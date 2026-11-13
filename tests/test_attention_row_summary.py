"""Needs attention's opened row is a summary, never the incident (the GUI review's item 1,
C3449; the operator, 2026-11-13: "Build review items 1, 2, 5, 6, 9 first"). Through the real
app, on the heal's lab (tests/test_incident_page.py's planted incidents, each by the heal
modules' own writers) and on the lost-stream row tests/test_seen_before.py builds from the
alerts reader's value. No device, no network.

- **Opened, a row says what is wrong, whether it needs a person where the row says so, and its
  one action with how it clears**, in at most `WORDS` words and `BLOCKS` blocks before anything
  more is pressed. Measured in a real browser at 1280 px on 2026-11-13, before and after: a
  lost stream's row 414 words and 813 px, now 153 and 416; a proposal's row 534 and 1,141 (its
  card drawn by opening the row), now 141 and 347; a can't-fix's 228 and 863, now 135 and 457;
  a rolled-back heal's 255 and 855, now 160 and 431; a halt's 157 and 495, now 144 and 392.
- **Open the incident is the row's first link** where the row is about one incident with a
  page of its own, and pressing it lands on that page.
- **What the incident's page draws is not drawn again on the row:** the decision's facts and
  the steps Mercury took are on the page (What's wrong, What Mercury has done), read there.
- **Nothing a person needs is dropped:** what the incident's page does not draw (a lost
  stream's reachability, what Mercury cannot see, Seen before and its diagnosis; an alert's
  Explain; a can't-fix's diagnosis and AI analysis; the record) stays in the row, one level
  down under Details and Details for the record, each closed until pressed.
- **A row with no incident** (a halt, a lost stream) still names what is wrong, its action and
  how it clears.
- **An action's card is read and drawn when its action is pressed**, never by opening the row.

The rows a person opens are opened in a real browser (headless Firefox, unconfined), at
1280 px: what is seen is the browser's own answer (`innerText`, `checkVisibility`), never a
reading of the markup.
"""
import json
import re
from html import unescape
from html.parser import HTMLParser

import pytest

from tests import test_incident_page as T
from tests import test_seen_before as SBT
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)
from tests.test_seen_before import loki  # noqa: F401  (a fixture)
from tests.test_seen_before import world as stream_world  # noqa: F401  (a fixture)

NET = T.NET
#: The opened row's limit before anything more is pressed: the words a person sees, and the
#: blocks they are in. The most measured on 2026-11-13 is 160 words (a rolled-back heal's
#: can't-fix), in six blocks, the last two each one closed line (Details, Details for the
#: record); the words' limit is that and 12%. Before it, a lost stream's opened row was nine
#: blocks and 414 words.
WORDS = 180
BLOCKS = 6
#: Its height at 1280 px, in a real browser: the tallest measured is 457 px.
HEIGHT_PX = 500
#: The blocks an opened row may hold, by the class that names each, in their order (the rows
#: folded under a collector's item are its seventh, never one of a planted row's here).
ORDER = ("att-incident", "att-wrong", "att-todo", "att-folded", "att-meta", "att-more",
         "att-record")
PLANTS = {"cant_fix": T.cant_fix, "rolled_back": T.rolled_back, "proposal": T.proposed}


def named(classes: list) -> list:
    """Each block by the one class of `ORDER` it carries (a lost stream's lead and its Does it
    need you? are one block, `att-fix`: what is wrong)."""
    out = []
    for cls in classes:
        cls = cls.split()
        names = [c for c in ORDER if c in cls] or (["att-wrong"] if "att-fix" in cls else [])
        assert len(names) == 1, f"a block the summary does not name: {cls}"
        out.append(names[0])
    return out


def a_summary(words: int, blocks: list, said: str):
    """What every opened row holds to, whatever it is about."""
    assert words <= WORDS, (words, said)
    assert len(blocks) <= BLOCKS, blocks
    assert blocks == [n for n in ORDER if n in blocks], ("the summary's order", blocks)
    assert "att-wrong" in blocks and "att-todo" in blocks, blocks
    assert "what to do" in said.lower() and "clears when" in said.lower(), said


def low(text) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", str(text))).split()).lower()


# ── In a real browser: the heal's rows, opened by their line ───────────────────────────────

SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
#: One opened row as the browser shows it: its body's words, its height, the blocks with
#: something to see, its first link seen, how many of its disclosures are open, the buttons
#: seen, and how many of the moved blocks its markup holds at all.
SEEN = r"""
var d = document.querySelector(arguments[0]), body = d.querySelector(':scope > .att-body');
function seen(e) { return e.checkVisibility() && (e.innerText || '').trim().length > 0; }
var a = Array.from(body.querySelectorAll('a')).filter(seen)[0];
return JSON.stringify({
  open: d.open,
  said: (body.innerText || '').replace(/\s+/g, ' ').trim(),
  height: Math.round(d.getBoundingClientRect().height),
  blocks: Array.from(body.children).filter(seen).map(function (e) { return e.className; }),
  first: a ? [a.innerText.trim(), a.getAttribute('href')] : null,
  opened: Array.from(body.querySelectorAll('details')).filter(
    function (x) { return x.open; }).length,
  buttons: Array.from(body.querySelectorAll('button')).filter(
    function (e) { return e.checkVisibility(); }).map(function (e) { return e.innerText.trim(); }),
  moved: body.querySelectorAll('.heal-facts, [data-run-stepper], .att-taken').length
});
"""
HEADS = ("return Array.from(document.querySelector(arguments[0]).querySelectorAll(arguments[1]))"
         ".filter(function (e) { return e.checkVisibility(); })"
         ".map(function (e) { return e.textContent.trim(); })")


@pytest.mark.parametrize("world", sorted(PLANTS))
def test_an_opened_row_is_a_summary_in_a_real_browser(client, monkeypatch, world):  # noqa: F811
    """Each planted heal row, opened by its line at 1280 px: a summary within the limits, Open
    the incident its first link where it has a page (none for a halt), every disclosure
    closed and no card drawn; the facts and the steps not on the row. Then pressed: Details
    shows a can't-fix's diagnosis and AI analysis, Details for the record its operands, Review
    the fix… the proposal's card, and Open the incident the incident's own page, which holds
    the facts and the steps."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests below still run")
    import app as nmas
    from modules import attention

    planted = PLANTS[world]()
    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    monkeypatch.setattr(attention, "CANT_FIX_DAYS", 10 ** 5)
    rows = attention.needs_attention()["rows"]
    assert rows and [r for r in rows if r.get("incident_page")], rows
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url(f"/v2/?list={NET}"))
            b.wait_for("return !!window.htmx && !!document.querySelector('#attention "
                       f"details.att') && {SETTLED}", 20)
            assert b.js("return document.querySelectorAll('#attention a[data-incident]')"
                        ".length") == len([r for r in rows if r.get("incident_page")])
            landed = None
            for r in rows:
                row = f'#attention details.att[data-attention-row="{r["id"]}"]'
                b.click(f"{row} > summary.att-line .att-what")
                b.wait_for(f"return document.querySelector(arguments[0]).open && {SETTLED}",
                           10, row)
                got = json.loads(b.js(SEEN, row))
                words = len(got["said"].split())
                blocks = named(got["blocks"])
                a_summary(words, blocks, got["said"])
                assert got["height"] <= HEIGHT_PX, got["height"]
                assert got["opened"] == 0, "every disclosure under the summary is closed"
                assert got["moved"] == 0, "the facts and the steps are not on the row"
                page = r.get("incident_page")
                lead = ("open the incident " if page else "") + low(r["cause"])[:50]
                assert got["said"].lower().startswith(lead), (lead, got["said"])
                for said in (r["action"]["label"], "Clears when " + r["clears"]["when"]):
                    assert low(said) in got["said"].lower(), said
                if page:
                    assert blocks[0] == "att-incident"
                    assert got["first"] == ["Open the incident",
                                            f"/v2/incident/{page['id']}?list={NET}"]
                    landed = r
                else:
                    assert blocks[0] == "att-wrong" and "att-incident" not in blocks
                    assert got["first"][0] != "Open the incident", got["first"]
                # Details: closed, it shows nothing; pressed, what the incident's page does
                # not draw (a can't-fix's diagnosis and its AI analysis).
                if r.get("heal_diagnosis"):
                    more = f"{row} > .att-body > details.att-more"
                    assert b.js(HEADS, more, "h3") == []
                    b.click(f"{more} > summary")
                    b.wait_for("return document.querySelector(arguments[0]).open", 10, more)
                    assert b.js(HEADS, more, "h3") == ["Mercury's diagnosis", "AI analysis"]
                    assert b.js("return document.querySelector(arguments[0])"
                                ".querySelectorAll('details').length", more) == 0
                # Details for the record: closed; pressed, every operand of the row.
                record = f"{row} > .att-body > details.att-record"
                assert b.js(HEADS, record, "dt") == []
                b.click(f"{record} > summary")
                b.wait_for("return document.querySelector(arguments[0]).open", 10, record)
                assert b.js(HEADS, record, "dt") == [k for k in r["operands"] if k != "members"]
            if world == "proposal":
                # Opening the row drew no card; Review the fix…, on the row's line, draws it.
                card = f'{row} > .att-body details.att-card'
                assert got["buttons"] == [] and "review the fix…" in got["said"].lower()
                assert b.js("return document.querySelector(arguments[0]).open", card) is False
                b.js("document.querySelector('a.att-jump[href=\"#heal-prop-"
                     f"{planted['id']}\"]').click(); return 1")
                b.wait_for("return document.querySelector(arguments[0]).open && "
                           "!!document.querySelector('.heal-prop .heal-form [name=reason]')",
                           15, card)
                assert b.js("return document.querySelector('.heal-prop button.btn-primary')"
                            ".checkVisibility()") is True
            # Open the incident: the incident's own page, holding what the row no longer draws.
            row = f'#attention details.att[data-attention-row="{landed["id"]}"]'
            b.click(f"{row} .att-incident a")
            b.wait_for("return location.pathname === arguments[0] && "
                       "!!document.querySelector('#inc-wrong .heal-facts')", 15,
                       f"/v2/incident/{landed['incident_page']['id']}")
            wrong = b.js("return document.querySelector('#inc-wrong').innerText")
            for fact in landed["heal_cause"]["facts"]:
                assert low(fact["text"]) in low(wrong), fact
            if landed.get("steps_taken"):
                assert b.js("return !!document.querySelector('#inc-done [data-run-stepper]')")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


@pytest.mark.parametrize("world", sorted(PLANTS))
def test_what_the_incident_s_page_draws_is_not_drawn_again_on_the_row(client, monkeypatch,  # noqa: F811
                                                                      world):
    """The decision's facts and the steps Mercury took: off the row, and on the incident's page
    under What's wrong and What Mercury has done, read there (a read that writes nothing)."""
    from modules import attention

    PLANTS[world]()
    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    monkeypatch.setattr(attention, "CANT_FIX_DAYS", 10 ** 5)
    (r,) = [x for x in attention.needs_attention()["rows"] if x.get("incident_page")]
    facts = [f["text"] for f in r["heal_cause"]["facts"]]
    assert facts, "the planted row carries the decision's facts"
    listed = T.read(client, f"/v2/attention?list={NET}").get_data(as_text=True)
    mine = listed.split(f'data-attention-row="{r["id"]}"', 1)[1]
    for moved in ('class="set-list heal-facts"', "data-run-stepper", 'class="att-taken"',
                  "The steps Mercury took", "<h3>Why this happened</h3>"):
        assert moved not in mine, f"{moved} is drawn on the row again"
    for fact in facts:
        assert T.text_of(fact) not in T.text_of(mine), fact
    inc = T.page(client, r["incident_page"]["id"])
    wrong = inc.split('id="inc-wrong"', 1)[1].split('id="inc-done"', 1)[0]
    done = inc.split('id="inc-done"', 1)[1].split('id="inc-todo"', 1)[0]
    assert 'class="set-list heal-facts"' in wrong
    for fact in facts:
        assert T.text_of(fact) in T.text_of(wrong), fact
    if r.get("steps_taken"):
        assert "data-run-stepper" in done, "the steps are on the incident's page"
        assert "Written by Mercury from its own record: no AI." in done


# ── A lost stream's row, drawn from the alerts reader's value ──────────────────────────────

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}


class Body(HTMLParser):
    """One row's body as drawn, split by what a closed disclosure hides: ``said`` (outside
    every closed disclosure, whose summary alone counts, and outside what the page hides
    until asked: ``x-cloak``, ``sr-only``), ``under`` (inside one) and ``blocks`` (the classes
    of the body's own children that say something)."""

    def __init__(self, row_id):
        super().__init__(convert_charrefs=True)
        self.row_id, self.armed, self.stack, self.done = row_id, False, None, False
        self.seen, self.hidden, self.blocks = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if self.done:
            return
        if self.stack is None:
            if tag == "details" and a.get("data-attention-row") == self.row_id:
                self.armed = True
            elif self.armed and tag == "div" and "att-body" in cls:
                self.stack = [(False, None)]
            return
        if tag in VOID:
            return
        hidden, closed = self.stack[-1]
        hide = hidden or "x-cloak" in a or "sr-only" in cls or (closed is True
                                                                and tag != "summary")
        if len(self.stack) == 1:
            self.blocks.append([" ".join(cls), 0])
        self.stack.append((hide, ("open" not in a) if tag == "details" else None))

    def handle_endtag(self, tag):
        if self.stack is None or self.done or tag in VOID:
            return
        self.stack.pop()
        self.done = not self.stack

    def handle_data(self, data):
        if self.stack is None or self.done or not data.split():
            return
        if self.stack[-1][0]:
            self.hidden.append(data)
            return
        self.seen.append(data)
        if len(self.stack) > 1:
            self.blocks[-1][1] += len(data.split())

    @property
    def said(self):
        return " ".join(" ".join(self.seen).split())

    @property
    def under(self):
        return " ".join(" ".join(self.hidden).split())


def test_a_lost_stream_keeps_its_action_and_everything_else_under_details(stream_world,  # noqa: F811
                                                                         loki):  # noqa: F811
    """A row with no incident. Its lead, Does it need you?, What to do and how it clears are
    the summary; whether the device answers, what Mercury cannot see, Seen before, Mercury's
    diagnosis and Explain have no incident page to be on, so they stay in the row, under
    Details; and its card is under its own button, closed."""
    SBT.past_loss()
    (row,) = SBT.rows_of(SBT.lost())
    assert row.get("packs"), "an alert's row knows its evidence pack"
    assert not row.get("incident_page")
    page = SBT.drawn([row])
    b = Body(row["id"])
    b.feed(page)
    assert b.done, "the row's body is drawn"
    blocks = named([cls for cls, n in b.blocks if n])
    a_summary(len(b.said.split()), blocks, b.said)
    assert blocks == ["att-wrong", "att-todo", "att-meta", "att-more", "att-record"], blocks
    assert b.said.startswith(SBT.LEAD + " " + SBT.NEEDS + " What to do"), b.said
    assert "Re-subscribe r2's telemetry (101, 102)" in b.said
    fix = row["fix"]
    for words in (fix["answers"]["words"], fix["unseen"], "Seen before on r2",
                  "Mercury's diagnosis:", "Explain", row["cause"], "seen_before",
                  "silence_measured"):
        assert T.text_of(words) in b.under, words
        assert T.text_of(words) not in b.said, words
    # Its card is asked for when Re-subscribe… is pressed: closed, under its own button.
    card = page.split('<details class="att-card"', 1)[1].split("</details>", 1)[0]
    assert " open" not in card.split(">", 1)[0]
    assert "Re-subscribe r2's telemetry (101, 102)…</summary>" in unescape(card)
    assert ('id="resub-r2" hx-get="/v2/device/r2/resubscribe?' in card
            and 'hx-trigger="toggle once from:closest details.att-card"' in card)
