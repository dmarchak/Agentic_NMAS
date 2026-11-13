"""Incident titles in plain words, and each fact once on the incident page and the heal card
(the GUI review's items 5 and 6, C3453 and C3454; the operator approved them, 2026-11-13;
docs/UI_RULES.md, "A title is a summary of at most 70 characters", "Each fact once,
measured", "The stepper never says "failed" for a decision that worked", "A stepper uses
labels of 2 to 4 words"). Through the real app on the heal's lab (tests/test_incident_page.py's
planted incidents, each by the heal modules' own writers). No device, no network.

The review measured: the incident page's h1 was the configuration line (95 characters, two
lines at 1280 px), repeated as the breadcrumb's last crumb; "verify failed" five times on the
rolled-back incident's page; the can't-fix stepper's one stage "Decide failed" in red; the heal
card's Decided stage the whole configuration line (five lines in a 150 px column); and its
Fixing and Checking stages each the failure's whole sentence.

- **One title builder** (`said.title`): every planted incident's title is at most 70
  characters and holds none of the configuration lines, trigger words or program lines its
  records hold, no mnemonic, no code key, no id and no address; the h1, the breadcrumb's last
  crumb (its whole on the hover) and the window's title are that one string; Needs attention's
  and History's lines lead with the same words; the configuration line is What's wrong's.
- **Each fact once:** every planted page says "verify failed" at most once, and a failed
  step's own words at most once (the first failed stage's exactly once); the heal card History
  reopens says each failure's words once too.
- **A decision that worked is never failed:** the can't-fix's stage reads "Can't fix: needs a
  person", drawn `needs` (amber, `--warn-mark`), and its stepper holds no "failed".
- **Each stage's sentence is at most `run_stepper.STAGE_SAID_WORDS` words**, its whole one
  level down.
- **In a real browser at 1280 px** (headless Firefox, unconfined): the longest planted title's
  h1 is one line, and the crumb one line with the title on its hover.
"""
import re
from html import unescape

import pytest

from modules import incident_page as IP
from modules import run_stepper as RS
from modules.heal import said
from tests import test_incident_page as T
from tests import test_incident_state as S
from tests.test_heal_act import ADJ
from tests.test_heal_decide import GOLDEN, ROUTE4
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_policy import T0
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = T.NET


def cleared():
    got = T.I.sight(NET, "edge-b", T.CFG, now=T0 - 1000)
    assert T.I.close_watching(NET, "self-healing was turned off", now=T0) == [got["incident"]]
    return got["incident"]


def failing(outcome):
    """A heal sent and not passing its verify, by the act's fake for *outcome*."""
    fake = {"rolled_back": {"post": GOLDEN + ROUTE4}, "partial": {"recheck": "drifted"},
            "symptom_remains": {"symptom": {"state": "present", "words": (
                "the OSPF adjacency edge-b – core-a is still down")}},
            "failed": {"result": {"outcome": "failed", "stage": "verify", "commands": ["x"],
                                  "reason": "verify did not pass"}},
            "refused": {"read_error": "timed out"}}[outcome]

    def plant():
        iid, got = T.heal(triggers=[T.CFG, ADJ] if outcome == "symptom_remains" else None,
                          **fake)
        assert got["outcome"] == outcome, got["words"]
        return iid
    return plant


#: Every kind of incident the heal's lab plants, by its own writers.
PLANTS = {"healed": T.healed, "rolled_back": T.rolled_back, "cant_fix": T.cant_fix,
          "proposal": S.proposal, "watching": S.watching, "approved": T.approved,
          "declined": T.declined, "busy": lambda: T.busy()[0], "cleared": cleared,
          "partial": failing("partial"), "symptom_remains": failing("symptom_remains"),
          "failed": failing("failed"), "refused": failing("refused")}
#: What a title never holds, by its shape (docs/UI_RULES.md; the email's EM4 shapes): a
#: quoted line, a log's mnemonic, a code key in snake case, an id, a hash, an address.
NEVER = re.compile(r"[“”\"`]|\b[A-Z]{2,}-\d-[A-Z_]+\b|\b[a-z]+_[a-z_]+\b|\bh[id]-[0-9a-f]{12}\b"
                   r"|\b[0-9a-f]{12,}\b|\b\d{1,3}(\.\d{1,3}){3}\b|\b[0-9a-f]{0,4}(:[0-9a-f]{0,4}){2,}")


def raw(iid) -> tuple:
    """`T.raw`, for an incident nothing has decided on too (no decision store is written):
    ``(the incident, its step-log rows, its decision store's lines)``."""
    import json
    import os

    inc = next(i for i in T.I.read(NET)["incidents"] if i["id"] == iid)
    rows = [r for r in T.SL.read(NET)["rows"] if r.get("incident") == iid]
    lines = []
    if os.path.exists(T.DS.path(NET)):
        with open(T.DS.path(NET), encoding="utf-8") as fh:
            lines = [d for d in (json.loads(x) for x in fh if x.strip())
                     if d.get("incident") == iid]
    return inc, rows, lines


def lines_held(iid) -> list:
    """Every configuration line and recorded text the incident's stores hold, read raw: each
    decision's units' lines and sections, its program, and each trigger's own words."""
    inc, rows, lines = raw(iid)
    out = [t.get("words") or "" for t in inc.get("triggers") or []]
    for d in lines:
        for u in d.get("units") or []:
            for p in [u] + list(u.get("parts") or []):
                out += list(p.get("add") or []) + list(p.get("remove") or [])
                out.append(p.get("section") or "")
        out += list(d.get("program") or [])
    for r in rows:
        out += list(r.get("program") or [])
    return [x.strip() for x in out if len(x.strip()) > 6]


def faults(title: str, held: list) -> list:
    """What makes *title* not a title: over 70 characters, a line its records hold, or a
    shape it never holds."""
    out = [f"{len(title)} characters"] if len(title) > said.TITLE_MAX else []
    out += [f"holds {x!r}" for x in held if x in title]
    out += [f"holds {m.group(0)!r}" for m in NEVER.finditer(title)]
    return out


def h1_of(body: str) -> str:
    return T.text_of(body.split("<h1", 1)[1].split(">", 1)[1].split("</h1>", 1)[0])


def live(body: str) -> str:
    return body.split('id="incident-live"', 1)[1].split('class="card tl-record-d', 1)[0]


# ── Titles: one builder, plain words, at most 70 characters ────────────────────────────────

class TestTheTitle:
    @pytest.mark.parametrize("name", sorted(PLANTS))
    def test_every_planted_incident_s_title_is_a_title(self, client, measured, name):  # noqa: F811
        iid = PLANTS[name]()
        body = T.page(client, iid)
        title = h1_of(body)
        assert title == IP.title(*T.model(iid)) and title.startswith("edge-b: "), title
        assert faults(title, lines_held(iid)) == [], (title, faults(title, lines_held(iid)))
        # The breadcrumb's last crumb and the window's title are the same string, the whole
        # on the crumb's hover.
        crumb = re.search(r'<span class="crumb-last" title="([^"]*)">(.*?)</span>', body)
        assert crumb and unescape(crumb.group(1)) == title == T.text_of(crumb.group(2))
        assert unescape(body.split("<title>", 1)[1].split(" · ", 1)[0]) == title

    def test_the_scan_finds_the_line_a_title_once_held(self, client):
        """The floor: the title the review measured (the configuration line, as
        `said.changes_words` words it) is found by both halves of the scan."""
        iid = T.rolled_back()
        _inc, _rows, lines = raw(iid)
        units = [u for d in lines for u in d.get("units") or []]
        old = f"edge-b: {said.changes_words(units)}"
        found = faults(old, lines_held(iid))
        assert any(f.startswith("holds 'ip route") for f in found), found
        assert any("“" in f for f in found) and f"{len(old)} characters" in found, found

    @pytest.mark.parametrize("name", ["healed", "rolled_back", "cant_fix", "proposal"])
    def test_the_configuration_line_is_what_s_wrong_s(self, client, measured, name):  # noqa: F811
        """The line the title no longer holds is said under What's wrong."""
        iid = PLANTS[name]()
        _inc, _rows, lines = raw(iid)
        units = [u for d in lines for u in d.get("units") or []]
        wrong = T.text_of(S.section(T.page(client, iid), "inc-wrong"))
        line = (units[0].get("remove") or units[0].get("add"))[0].strip()
        assert line in wrong and line not in IP.title(*T.model(iid)), (line, wrong)

    @pytest.mark.parametrize("name", ["proposal", "cant_fix", "busy"])
    def test_needs_attention_leads_with_the_same_words(self, client, monkeypatch,  # noqa: F811
                                                       measured, name):  # noqa: F811
        """ONE builder: a decision's row on Needs attention leads with what happened as its
        incident's page titles it (an open incident's title has no ending)."""
        from modules import attention

        S.with_its_item(monkeypatch)
        iid = PLANTS[name]()
        title = IP.title(*T.model(iid))
        (row,) = [r for r in attention.needs_attention()["rows"]
                  if (r.get("incident_page") or {}).get("id") == iid]
        assert row["what"].startswith(title + ". "), (row["what"], title)

    @pytest.mark.parametrize("name", ["cant_fix", "busy"])
    def test_history_leads_with_the_same_words(self, client, name):
        """And its History line (a decision the decision's pass recorded in the step log;
        the planted proposal is recorded in the decisions store alone, so History holds no
        line for it)."""
        from modules import history_sources as HS
        from tests.test_heal_mark_and_held import _ctx

        iid = PLANTS[name]()
        title = IP.title(*T.model(iid))
        (event,) = [e for e in HS.heal(_ctx())["events"]
                    if ("Incident", iid) in list(e.get("record") or [])]
        assert event["what"].startswith(title + ". "), (event["what"], title)

    def test_a_decision_recorded_before_c3453_reads_the_same(self, client, monkeypatch):
        """A record an earlier release wrote keeps the configuration line as its stored line
        and may keep no cause: Needs attention, History and the page draw the title again
        from the decision's own record, and the line is said under What's wrong. The older
        record is the planted can't-fix's, read through the stores' own readers with its
        stored line and cause as an earlier release wrote them."""
        from modules import attention
        from modules import history_sources as HS
        from modules.heal import decisions as HD
        from modules.heal import steplog
        from tests.test_heal_mark_and_held import _ctx

        S.with_its_item(monkeypatch)
        iid = T.cant_fix()
        title = IP.title(*T.model(iid))
        _inc, _rows, lines = raw(iid)
        units = [u for d in lines for u in d.get("units") or []]
        old = f"edge-b: {said.changes_words(units)}. Mercury cannot fix it by itself"

        def older(x):
            return dict(x, headline=old, cause=None) if x.get("incident") == iid else x

        read_d, read_all, read_one = HD.decisions, steplog.incidents, steplog.incident
        monkeypatch.setattr(HD, "decisions", lambda n: [older(d) for d in read_d(n)])
        monkeypatch.setattr(steplog, "incidents", lambda n, *a, **kw: dict(
            read_all(n, *a, **kw), entries=[older(e) for e in read_all(n, *a, **kw)["entries"]]))
        monkeypatch.setattr(steplog, "incident", lambda n, i: older(read_one(n, i) or {}))
        assert HD.decisions(NET)[-1]["headline"] == old, "the older record is what is read"
        (row,) = [r for r in attention.needs_attention()["rows"]
                  if (r.get("incident_page") or {}).get("id") == iid]
        assert row["what"].startswith(title + ". "), (row["what"], title)
        (event,) = [e for e in HS.heal(_ctx())["events"]
                    if ("Incident", iid) in list(e.get("record") or [])]
        assert event["what"].startswith(title + ". "), (event["what"], title)
        body = T.page(client, iid)
        assert h1_of(body) == title
        wrong = T.text_of(S.section(body, "inc-wrong"))
        assert f"What changed on edge-b: {said.changes_words(units)}." in wrong, wrong

    def test_the_builder_s_words_and_bound(self):
        """`said.title` on units, symptoms and nothing, an IPv6 line beside its IPv4 one, and
        a name long enough to need the bound: "outside Mercury" goes first, then an
        ellipsis."""
        def unit(line, op="remove", section=None):
            return {"op": op, "section": section or line, "add": [line] if op != "remove"
                    else [], "remove": [line] if op == "remove" else []}
        cfg = [{"kind": "config_change"}]
        assert said.title("r1", [unit("ip route 192.0.2.0 255.255.255.0 192.0.2.1")],
                          cfg) == "r1: static route added outside Mercury"
        assert said.title("r1", [unit("ipv6 route 2001:db8::/64 2001:db8::1")], cfg) == \
            "r1: IPv6 static route added outside Mercury"
        assert said.title("r1", [unit("router-id 192.0.2.9", "change", "router ospf 1")
                                 | {"add": ["router-id 192.0.2.1"],
                                    "remove": ["router-id 192.0.2.9"]}]) == \
            "r1: OSPF router-id changed"
        assert said.title("r1", [unit("logging host 192.0.2.5", "add")] * 2) == \
            "r1: 2 logging hosts removed"
        assert said.title("r1", [], [{"kind": "adjacency_log", "protocol": "OSPF",
                                      "peer": "core-a", "neighbor": "192.0.2.2"}]) == \
            "r1: OSPF neighbour core-a lost"
        assert said.title("r2", [], [{"kind": "alert", "subscription": "101"},
                                     {"kind": "alert", "subscription": "102"}]) == \
            "r2: 2 telemetry streams lost"
        assert said.title("r1") == ""
        long = "a-router-with-a-name-long-enough-to-need-the-whole-bound"
        got = said.title(long, [unit("ip route 192.0.2.0 255.255.255.0 192.0.2.1")], cfg)
        assert len(got) <= said.TITLE_MAX and got.endswith("…") and \
            "outside" not in got, got
        assert said.title("r1-long-name", [unit("ip route 192.0.2.0 255.255.255.0 192.0.2.1")],
                          cfg, room=40) == "r1-long-name: static route added"


# ── Each fact once ─────────────────────────────────────────────────────────────────────────

def failures(iid) -> list:
    """Each failed step's own words, as the act recorded them (read raw), in the order the
    act recorded them: the failure's sentences."""
    _inc, rows, _lines = raw(iid)
    return [s["words"] for r in rows if r.get("row") == "act" for s in r.get("steps") or []
            if s.get("result") in ("failed", "present", "refused") and s.get("step") != "record"
            and len(s.get("words") or "") >= RS.TOLD_CHARS]


class TestEachFactOnce:
    @pytest.mark.parametrize("name", sorted(PLANTS))
    def test_a_failure_is_said_once(self, client, measured, name):  # noqa: F811
        iid = PLANTS[name]()
        words = T.text_of(live(T.page(client, iid)))
        assert words.count("verify failed") <= 1, words
        for sentence in failures(iid):
            assert words.count(sentence) <= 1, (sentence, words)

    @pytest.mark.parametrize("name", ["rolled_back", "failed", "partial", "symptom_remains"])
    def test_a_failed_verify_says_it_once_and_its_sentence_once(self, client, name):
        """Measured before: five times on the rolled-back page. "verify failed" once (the
        attempt line), the first failure's sentence once (its stage, on its step's line), on
        the page and on the card its device's History reopens."""
        iid = PLANTS[name]()
        body = T.page(client, iid)
        words = T.text_of(live(body))
        first = failures(iid)
        assert words.count("verify failed") == 1, words
        assert first and all(words.count(s) == 1 for s in first[:1]), (first, words)
        card = T.read(client, f"/v2/device/edge-b?list={NET}&tab=history&result={iid}")
        stages = re.search(r'<ol class="run-stages".*?</ol>\s*</div>',
                           card.get_data(as_text=True), re.S).group(0)
        assert T.text_of(stages).count(first[0]) == 1, T.text_of(stages)

    def test_the_rolled_back_card_says_its_failure_where_it_happened(self, client):
        """The Fixing stage (the Apply) says why; Checking and Done say their state."""
        body = T.page(client, T.rolled_back())
        said_ = dict(re.findall(r'data-stage="(\w+)".*?class="run-stage-said"[^>]*>(.*?)</span>',
                                body, re.S))
        assert said_["fixing"].startswith("Apply failed: "), said_
        assert said_["checking"] == "Check intent failed", said_
        assert said_["done"].startswith("Rolled back"), said_

    @pytest.mark.parametrize("name", ["cant_fix", "busy"])
    def test_a_can_t_fix_needs_a_person_and_never_reads_failed(self, client, measured, name):  # noqa: F811
        done = S.section(T.page(client, PLANTS[name]()), "inc-done")
        (stage,) = re.findall(r'<li class="run-stage run-stage-(\w+)" data-stage="decided"',
                              done)
        assert stage == "needs"
        said_ = re.search(r'data-stage="decided".*?class="run-stage-said"[^>]*>(.*?)</span>',
                          done, re.S).group(1)
        assert unescape(said_) == "Can't fix: needs a person", said_
        assert "run-mark-needs" in done and "role=\"alert\"" not in done
        stepper = done.split("data-run-stepper", 1)[1]
        assert "failed" not in T.text_of(stepper).lower(), T.text_of(stepper)

    def test_needs_is_drawn_amber_never_red(self):
        """The colour token: every rule naming the `needs` state draws it with the warning
        mark, and none with danger."""
        import os
        css = open(os.path.join(os.path.dirname(__file__), "..", "static", "css",
                                "nmas-v2.css"), encoding="utf-8").read()
        rules = re.findall(r"([^{}]*\brun-(?:stage|step|mark)-needs\b[^{}]*)\{([^}]*)\}", css)
        assert len(rules) >= 4, rules
        assert all("--danger" not in body for _sel, body in rules), rules
        assert all("--warn" in body for _sel, body in rules), rules

    @pytest.mark.parametrize("name", sorted(PLANTS))
    def test_every_stage_says_at_most_twelve_words(self, client, measured, name):  # noqa: F811
        body = T.page(client, PLANTS[name]())
        for said_ in re.findall(r'class="run-stage-said"[^>]*>(.*?)</span>\s*<span '
                                r'class="run-stage-time"', body, re.S):
            text = T.text_of(said_)
            assert RS.said_words(text) <= RS.STAGE_SAID_WORDS, text
            assert "“" not in text, f"a stage quotes a configuration line: {text}"

    def test_the_bound_cuts_and_keeps_the_whole_one_level_down(self):
        long = ("Applied 3 lines to edge-b, then waited out the hold, then read every one "
                "of its neighbours again (a long wait)")
        cut = RS.bounded(long)
        assert RS.said_words(cut) == RS.STAGE_SAID_WORDS and cut.endswith("…"), cut
        assert RS.bounded("Apply failed: one (two three four five six seven eight nine ten "
                          "eleven)") == "Apply failed: one…"
        assert RS.bounded("Healed and verified in 18 min 17 s") == \
            "Healed and verified in 18 min 17 s"
        # A stage whose operation's own sentence was cut keeps it whole above its steps.
        card = RS.record_card("edge-b", "steps", [RS.from_record(
            (("a", "Apply"),), [{"step": "a", "result": "ok", "words": "x"}], ended=True)],
            ended=True, level="ok")
        got = RS.stages(card, (("fixing", "Fixing", ("a",)),), ended=True,
                        sentence=lambda g: long)
        (g,) = got["stages"]
        assert g["sentence"] == cut and g["long"] == long


# ── In a real browser ──────────────────────────────────────────────────────────────────────

class TestInARealBrowser:
    def test_the_longest_title_is_one_line_at_1280(self, client):
        """The healed incident's title, the longest planted (it carries its ending), is one
        line at 1280 px, and the crumb one line with the whole title on its hover."""
        from tests import browser

        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the titles' bound above still runs")
        import app as APP

        iid = T.healed()
        title = IP.title(*T.model(iid))
        assert len(title) >= 60, title
        kept = (T.I.read(NET), T.SL.read(NET), T.DS.read(NET))
        crumb = ("var c = document.querySelector('.crumb-last'); return c && [c.scrollWidth > "
                 "c.clientWidth, getComputedStyle(c).textOverflow, c.title, "
                 "c.getBoundingClientRect().height, parseFloat(getComputedStyle(c).lineHeight)];")
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1280, "height": 1000})
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                got = b.wait_for(
                    "var h = document.getElementById('inc-title'),"
                    " c = document.querySelector('.crumb-last');"
                    "if (!h || !c) return null;"
                    "var lh = parseFloat(getComputedStyle(h).lineHeight),"
                    " cl = parseFloat(getComputedStyle(c).lineHeight);"
                    "return [window.innerWidth, h.getClientRects().length,"
                    " h.getBoundingClientRect().height, lh, c.getBoundingClientRect().height,"
                    " cl, c.title, h.textContent.trim()];")
                # Narrower than the crumb's row (the window's narrowest, about 500 px): the
                # crumb is cut with an ellipsis on one line, the whole title on its hover.
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 500, "height": 1000})
                narrow = b.wait_for(crumb)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        width, _rects, height, line, crumb_h, crumb_line, hover, text = got
        assert width >= 1200, got
        assert height < 1.5 * line, f"the h1 is {height} px tall, its line {line} px: {got}"
        assert crumb_h < 1.5 * crumb_line, got
        assert hover == title and text == title, got
        cut, overflow, whole, cut_h, cut_line = narrow
        assert cut and overflow == "ellipsis" and whole == title, narrow
        assert cut_h < 1.5 * cut_line, f"the cut crumb wraps: {narrow}"
        assert (T.I.read(NET), T.SL.read(NET), T.DS.read(NET)) == kept, \
            "the page, opened in a real browser, left the heal's stores as they were"
