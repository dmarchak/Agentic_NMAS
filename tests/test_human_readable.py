"""No dead identifiers (docs/MERCURY_CHARTER.md, "Human-facing means human-readable", rule 2;
the operator, 2026-11-08): an incident ID, decision ID, hash, commit or policy ID is never the
primary content; each one shown is a link to the page for the thing it names, or it sits under
a collapsed "Details for the record" disclosure. And rule 5 (the operator, 2026-11-08): "Never
send a person to look up what Mercury already knows. 'Find who changed it on History' is a
bug."

**The surfaces, rendered through the real app** on test_heal_decide's lab (Default marked lab,
dry run; no device, no network), holding the three heal records that carry identifiers today,
each made by the real decision from a fake device read: a dry-run decision on edge-b (an added
route, would heal), a Tier 2 proposal on edge-c (a changed router-id) and a can't-fix on edge-d
(a security ACL), told to a team by email through the real notifier and relay (its SMTP a
fake, tests/test_notify.py's `env`):

- `needs_attention`: the Needs attention page (/v2/), drawn from the heal source alone
  (`attention.SOURCES`: this view is a subset, so a row another source reads from this
  checkout's own state, a host step from its git history, never moves the count), and each
  slot a row loads when it is opened (its `hx-get` on a `toggle` trigger: the proposal's card,
  the can't-fix's analysis), read as a person sees it once the row is open;
- `history`: /v2/history of Default;
- `device`: the device page on its History tab, for edge-b and edge-d;
- `email`: the can't-fix's message as the relay built it, its subject and text.

**The scan** (`bare`): HTML parsed with `html.parser`, never matched as a substring. A visible
text node is in scope unless an ancestor is a link (`<a href>`) or a `<details>` without
`open` whose `<summary>` reads "Details for the record" (`RECORD`; whitespace normalised, case
as written) holds it (its summary is that name alone). Every other disclosure, open or collapsed,
is read as shown (the operator, 2026-11-08, decision 1: a History row or a Needs attention row
is a disclosure, and its body counts); text in `<script>`, `<style>` and `<template>` is not
drawn.
Attribute values are not text. In a plain-text email every identifier is bare unless it is part
of a URL (`http(s)://…`, or a Mercury path `/v2/…`). The patterns (`PATTERNS`): an incident id
(`hi-` and 6 or more hex), a decision id (`hd-`), a run of 12 or more hex characters (a hash, a
commit, a fingerprint, any other id), a guard label (`guard N`), and a heal step label in the
step log's form, "N. <step>", the step names those of `modules/heal/decide.py`,
`modules/heal/act.py` and `modules/heal/propose.py`'s `STEPS`. A run of hex inside an `hi-` or
`hd-` id is that id, counted once.

**The lookups** (`lookups`, the kind ``lookup``): text that tells the reader to find, see, look
(up, on, at, in), check or read something on History (`LOOKUP`, its verb anchored at the start
of a run, of an element's text or of a clause), read in runs (`runs`: the drawn text of one
block, so the words may span a link), in scope inside a link too (a link's words still send
the person away), never inside a collapsed "Details for the record"; a plain message's lines
each a run. Decision 2 (the operator, 2026-11-08): "read" stays a lookup verb.

**The backlog** (`KNOWN_BARE_IDENTIFIERS`): today's violations, each keyed by its surface, its
pattern's kind and a short context (the body's drawn text read as one, every identifier in it
replaced by its kind, every digit run by ``#``: the 40 characters before and 30 after), its
value how many times that key occurs, so a new violation of the same kind elsewhere is a new
key. A violation not in it, or a key occurring more often than it says, fails; a key
that no longer occurs as often fails too, so the list only shrinks (tests/ratchet_lists.py
registers it, `shrinks`: a new key or a risen count needs a Test-Weakened trailer).
"""

import html as _html
import re
import time
from collections import Counter
from html.parser import HTMLParser

import pytest

from tests.test_heal_analysis import ACL_RUNNING
from tests.test_heal_analysis import ai  # noqa: F401  (the fixture, named by the tests below)
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `ai` builds on)
from tests.test_heal_policy import iso
from tests.test_heal_propose import R8, FakeApproved
from tests.test_heal_propose import measured  # noqa: F401  (the fixture, named below)
from tests.test_heal_triggers import _Lazy
from tests.test_notify import _mail, _relay, _team_with_email
from tests.test_notify import env  # noqa: F401  (the fixture, named below)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

DC, DS, SL, I = _Lazy("decide"), _Lazy("decisions"), _Lazy("steplog"), _Lazy("incidents")
HX = {"HX-Request": "true"}
SURFACES = ("needs_attention", "history", "device", "email")
#: The lab's three devices, one per heal record (documentation addresses).
DEVICES = (("edge-b", "192.0.2.21"), ("edge-c", "192.0.2.22"), ("edge-d", "192.0.2.23"))


def _step_names() -> tuple:
    from modules.heal import act, decide, propose

    return tuple(sorted({name for steps in (decide.STEPS, act.STEPS, propose.STEPS)
                         for name, _words in steps}, key=lambda n: (-len(n), n)))


#: Each pattern's kind and its expression, in the order a span is claimed: an id's hex is the
#: id's, never a second hash.
PATTERNS = (
    ("incident_id", re.compile(r"\bhi-[0-9a-f]{6,}\b")),
    ("decision_id", re.compile(r"\bhd-[0-9a-f]{6,}\b")),
    ("hex", re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{12,}(?![0-9A-Za-z])")),
    ("guard", re.compile(r"\b[Gg]uard \d+\b")),
    ("step", re.compile(r"(?<![\w.])\d{1,2}\. (?:" + "|".join(map(re.escape, _step_names()))
                        + r")\b")),
)
#: Rule 5 (the operator, 2026-11-08: "Never send a person to look up what Mercury already
#: knows. 'Find who changed it on History' is a bug"): an instruction to find, see, look (up,
#: on, at, in), check or read something on History. Anchored: the verb starts the run, an
#: element's text within it (`NODE`, where `runs` joins two), or a clause (after `. ; : ! ? (`,
#: or ", or|and|then", or "then"), so "each read on r3's History" (a noun) and "Open r3's
#: History" (the one action, a link) are not matched; History is named in the same sentence,
#: within 80 characters.
NODE = "\x00"
LOOKUP = re.compile(r"(?:^|(?<=[.;:!?(\x00])\s*|,\s*(?:or|and|then)\s+|\b[Tt]hen\s+)"
                    r"(?P<verb>[Ff]ind|[Ss]ee|[Ll]ook(?:\s+(?:up|on|at|in))?|[Cc]heck|[Rr]ead)"
                    r"\b[^.;!?]{0,80}?\bHistory\b")
#: The text no person is shown.
HIDDEN_TAGS = {"script", "style", "template"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr"}
#: A URL in a plain-text message: an address, or Mercury's own path.
URL = re.compile(r"https?://\S+|(?<![^\s(])/v2/\S*")
BEFORE, AFTER = 40, 30


def _cut(text: str, s: int, e: int) -> str:
    """*text* from `BEFORE` characters before *s* to `AFTER` after *e*, widened to whole words
    (a word is never cut in two, so an address in a context stays whole), its whitespace one
    space."""
    a, b = max(0, s - BEFORE), min(len(text), e + AFTER)
    while a > 0 and not text[a - 1].isspace() and text[a - 1] != NODE:
        a -= 1
    while b < len(text) and not text[b].isspace() and text[b] != NODE:
        b += 1
    return re.sub(r"\s+", " ", text[a:b].replace(NODE, " ")).strip()


def matches(text: str) -> list:
    """``[(kind, start, end)]``: each identifier in *text*, a span claimed once, in order."""
    out, taken = [], []
    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append((kind, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def _norm(text: str) -> str:
    """Digit runs to ``#`` and whitespace to one space, and an age drawn from the clock read
    as one: "just now" is "# min ago", so a context does not depend on how long the run took
    between the lab's records and the render (CI's runner drew "just now" where the laptop
    drew "# min ago", 33c2cfb1's run #1579)."""
    text = re.sub(r"\bjust now\b", "# min ago", text, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text))


def contexts(nodes: list) -> list:
    """``[(kind, context)]`` for each identifier to report in *nodes* (``[(text, [(kind,
    start, end, report)])]``, a body's drawn text in order): the drawn text read as one, every
    identifier in it replaced by ``<kind>``, digit runs by ``#`` and whitespace by one space,
    cut to the `BEFORE` characters before this one and `AFTER` after, in whole words (`_cut`).
    Read across nodes, so a hash alone in its own element is still told by what is drawn
    around it."""
    pieces, marks, length = [], [], 0

    def put(piece):
        nonlocal length
        pieces.append(piece)
        length += len(piece)

    for text, found in nodes:
        at = 0
        for kind, s, e, report in found:
            put(_norm(text[at:s]))
            if report:
                marks.append((kind, length, length + len(kind) + 2))
            put(f"<{kind}>")
            at = e
        put(_norm(text[at:]) + " ")
    whole = "".join(pieces)
    return [(kind, _cut(whole, s, e)) for kind, s, e in marks]


#: The one disclosure that takes what it holds out of scope (the operator, 2026-11-08, decision
#: 1: "narrow the exemption to a collapsed disclosure named 'Details for the record'. Row bodies
#: count as shown"): its summary's words, whitespace normalised, case as written.
RECORD = "Details for the record"
#: Where a `<details>`'s summary words are kept on its attributes while it is parsed (a key no
#: attribute name can be).
SUMMARY = ":summary"
#: The elements a run of text ends at: the text inside one of them, outside any nested one,
#: reads as one sentence (a lookup's words may span a link: "Read the record on <a>r3's
#: History</a>").
BLOCK = {"address", "article", "aside", "blockquote", "button", "caption", "dd", "details",
         "div", "dl", "dt", "fieldset", "figcaption", "footer", "form", "h1", "h2", "h3", "h4",
         "h5", "h6", "header", "label", "legend", "li", "main", "nav", "ol", "option", "p",
         "pre", "section", "select", "summary", "table", "td", "th", "tr", "ul"}


class _Scan(HTMLParser):
    """The drawn text nodes of a page, each with whether a link holds it, whether a collapsed
    "Details for the record" hides it, and the block it reads in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.nodes, self.serial = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        self.serial += 1
        self.stack.append((tag, dict(attrs), self.serial))

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        st = self.stack
        for i, (tag, attrs, _n) in enumerate(st[:-1]):
            if tag == "details" and st[i + 1][0] == "summary":
                attrs[SUMMARY] = attrs.get(SUMMARY, "") + data       # the summary's own words
        if not data.strip():
            return
        block = next((n for t, _a, n in reversed(st) if t in BLOCK), 0)
        self.nodes.append((data, self.state(), block))

    def state(self):
        """None when the text is not drawn, else ``(linked, collapsed)``: a link holds it; a
        `<details>` without `open` whose summary reads `RECORD` holds it
        (every other disclosure, open or collapsed, is read as shown)."""
        st = self.stack
        linked = collapsed = False
        for tag, attrs, _n in st:
            if tag in HIDDEN_TAGS:
                return None
            if tag == "a" and "href" in attrs:
                linked = True
            # Its summary is its name and nothing else, so it is held out with the rest.
            if tag == "details" and "open" not in attrs and \
                    " ".join(attrs.get(SUMMARY, "").split()) == RECORD:
                collapsed = True
        return linked, collapsed


def _drawn(page: str) -> list:
    p = _Scan()
    p.feed(page)
    p.close()
    return [(t, s, b) for t, s, b in p.nodes if s is not None]


def text_nodes(page: str) -> list:
    """``[(text, in_scope)]``: every drawn text node of *page*; *in_scope* False under a link
    or inside a collapsed "Details for the record". Undrawn text is left
    out."""
    return [(t, not (linked or collapsed)) for t, (linked, collapsed), _b in _drawn(page)]


def runs(page: str) -> list:
    """The text a person reads as one, outside every collapsed "Details for the record", links
    included: each run the consecutive drawn nodes of one block, joined by `NODE`."""
    out, last = [], None
    for text, (_linked, collapsed), block in _drawn(page):
        if collapsed:
            last = None
            continue
        if block == last:
            out[-1] += NODE + text
        else:
            out.append(text)
        last = block
    return out


def bare(body: str, *, plain: bool = False) -> list:
    """``[(kind, context)]``: each bare identifier of *body*, an HTML page, or with *plain* a
    plain-text message (each line a node, an identifier inside a URL not bare)."""
    nodes = []
    if plain:
        for line in body.splitlines():
            urls = [(m.start(), m.end()) for m in URL.finditer(line)]
            nodes.append((line, [(k, s, e, not any(us <= s and e <= ue for us, ue in urls))
                                 for k, s, e in matches(line)]))
    else:
        for text, in_scope in text_nodes(body):
            nodes.append((text, [(k, s, e, in_scope) for k, s, e in matches(text)]))
    return contexts(nodes)


def _masked(text: str) -> str:
    """*text* with every identifier replaced by ``<kind>``, digit runs by ``#``, whitespace
    by one space: what a lookup is matched in, and its context cut from."""
    out, at = [], 0
    for kind, s, e in matches(text):
        out += [text[at:s], f"<{kind}>"]
        at = e
    return _norm("".join(out + [text[at:]])).strip()


def lookups(body: str, *, plain: bool = False) -> list:
    """``[("lookup", context)]``: each place *body* sends the reader to History to find what
    Mercury already knows (rule 5; `LOOKUP`), in a link too (its words still send the person
    away), never inside a collapsed "Details for the record"; a plain message's lines each a
    run."""
    out = []
    for run in (body.splitlines() if plain else runs(body)):
        text = _masked(run)
        for m in LOOKUP.finditer(text):
            out.append(("lookup", _cut(text, m.start("verb"), m.end())))
    return out


def found(drawn: dict) -> Counter:
    """``{(surface, kind, context): count}`` over every rendered body of *drawn*: its bare
    identifiers and its lookups."""
    out = Counter()
    for surface, bodies in drawn.items():
        for _where, body, plain in bodies:
            for kind, ctx in bare(body, plain=plain) + lookups(body, plain=plain):
                out[(surface, kind, ctx)] += 1
    return out


# ── The lab: three heal records, the notice told, the surfaces rendered ────────────────────

def _settle(running, device, now, claim=True):
    """An incident on *device* settled on *running*'s departure at *now* (test_heal_decide's
    `settle`, its clock this test's, so Needs attention's windows hold it)."""
    from modules.drift_check import departure, drift_diff

    t = {"kind": "config_change", "key": f"cfg:{device}", "epoch": now - 1000,
         "at": iso(now - 1000), "attribution": {"by": "outside"},
         "person": {"user": "alice", "words": "the line names the account alice on vty0"},
         "words": "CONFIG_I"}
    inc_id = I.sight("Default", device, t, now=now - 1000)["incident"]
    dep = departure(drift_diff(GOLDEN, running, device))
    I.settle("Default", inc_id, {"state": "persisted", "words": "settled", "first": 0,
                                 "second": 1, "operands": {"departure": dep}}, now - 10)
    if not claim:
        return I.ready("Default")[-1]
    return I.claim("Default", inc_id, by="test", now=now - 5)


def _records(ai, env, monkeypatch, now):
    """The dry run, the proposal and the can't-fix, each by the real decision; the can't-fix
    told by email. ``{"proposal": its decision, "mail": the message}``."""
    from modules import config, heal_notice, heal_notify

    inc = _settle(GOLDEN + ROUTE4, "edge-b", now)
    made = DC.decide_one("Default", inc, now=now, sources=Fake(GOLDEN + ROUTE4))
    assert made["outcome"] == "would_heal", made["words"]
    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
    d = DS.record("Default", made, now)
    SL.record_decision("Default", dict(d, steps=steps, phase=phase), now)
    inc = _settle(R8, "edge-c", now)
    made = DC.decide_one("Default", inc, now=now, sources=Fake(R8))
    assert made["outcome"] == "propose", made["words"]
    proposal = DS.record("Default", made, now)
    _settle(ACL_RUNNING, "edge-d", now, claim=False)
    (cf,) = DC.run("Default", now=now, sources=Fake(ACL_RUNNING))["decided"]
    assert cf["outcome"] == "cant_fix", cf
    monkeypatch.setattr(config, "DATA_DIR", str(ai.dir))
    _relay(env)
    team, _dest = _team_with_email()
    monkeypatch.setattr(heal_notify, "teams_for", lambda network, event: [team])
    heal_notice.notice("Default", cf["incident"], send=ai.send, wait_s=5, now=now + 1)
    (mail,) = [_mail(raw) for s in env.smtp for raw in s.sent]
    return {"proposal": proposal, "mail": mail}


_TOGGLED = re.compile(r"<[^>]*\bhx-get=\"([^\"]+)\"[^>]*\bhx-trigger=\"[^\"]*\btoggle\b")


def _get(client, url, headers=None):
    r = client.get(url, headers=headers or {})
    assert r.status_code == 200, f"{url}: {r.status_code}"
    return r.get_data(as_text=True)


def render(made: dict, monkeypatch) -> dict:
    """``{surface: [(where, body, plain)]}``: each surface as the app draws it."""
    import app as A
    from modules import attention

    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    c = A.app.test_client()
    page = _get(c, "/v2/?list=Default")
    slots = [_html.unescape(u) for u in _TOGGLED.findall(page)]
    mail = made["mail"]
    return {
        "needs_attention": [("/v2/", page, False)]
        + [(u, _get(c, u, HX), False) for u in slots],
        "history": [("/v2/history", _get(c, "/v2/history?list=Default"), False)],
        "device": [(f"/v2/device/{h}", _get(c, f"/v2/device/{h}?tab=history&list=Default"),
                    False) for h in ("edge-b", "edge-d")],
        "email": [("the can't-fix's message",
                   f"{mail['Subject']}\n{mail.get_content()}", True)],
    }


@pytest.fixture
def drawn(ai, measured, env, monkeypatch):
    """The four surfaces rendered on the lab: ``{surface: [(where, body, plain)]}``."""
    now = time.time() - 600
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [
        {"hostname": h, "ip": ip, "device_type": "cisco_xe", "username": "nmas"}
        for h, ip in DEVICES])
    monkeypatch.setattr("modules.heal.propose.Sources", lambda net: FakeApproved(R8))
    made = _records(ai, env, monkeypatch, now)
    out = render(made, monkeypatch)
    out[":proposal"] = made["proposal"]
    return out


def _surfaces(drawn):
    return {k: v for k, v in drawn.items() if not k.startswith(":")}


#: Today's bare identifiers, the allowed backlog: ``(surface, kind, context): count``. It only
#: shrinks (tests/ratchet_lists.py, `shrinks`): each fixed one leaves, and a new key or a risen
#: count needs a Test-Weakened trailer naming its row. The lookups (kind ``lookup``) are held
#: here too. It started at the full count (the operator, 2026-11-08, decision 1: "The backlog
#: starts at the full count"), every row's body read as shown: 96 in 88 keys. C2817 and C2823
#: (2026-11-09) took out the heal records' own: their ids, hashes and steps under a collapsed
#: "Details for the record" on Needs attention and History, the email's steps by what they do,
#: and the two lookups drawn in place: 12 in 12 keys, the AI call's and the notification's
#: History rows and the email's foot.
KNOWN_BARE_IDENTIFIERS = {
    # The device page: edge-d's History tab (the AI call and notification rows).
    ('device', 'hex', 'By job:heal-notice-<incident_id> Call ai-<hex> About heal_incident Prompt heal_analysis.v#'): 1,
    ('device', 'hex', 'by email: sent attempt # of # Delivery d-<hex> Team Network ops Channel email'): 1,
    ('device', 'incident_id', '(claude-sonnet-#-#, $#.#) job:heal-notice-<incident_id> the background feature heal_analysis'): 1,
    ('device', 'incident_id', 'Channel email Recipient …@example.com Incident <incident_id> Attempt # of # Took #.# s # min'): 1,
    ('device', 'incident_id', 'estimate; nothing was sent By job:heal-notice-<incident_id> Call ai-<hex> About heal_incident'): 1,
    # The can't-fix's email: the incident's id in the foot (the same one, its context's words
    # moved 2026-11-12, C3187: the sent time local, the zone's line after it).
    ('email', 'incident_id', 'is not set: notify_link_base) Incident <incident_id> · sent #-#-# #:# Times are in'): 1,
    # History: the AI call and notification rows, and the Person filter's choice.
    ('history', 'hex', 'By job:heal-notice-<incident_id> Call ai-<hex> About heal_incident Prompt heal_analysis.v#'): 1,
    ('history', 'hex', 'by email: sent attempt # of # Delivery d-<hex> Team Network ops Channel email'): 1,
    ('history', 'incident_id', '(claude-sonnet-#-#, $#.#) job:heal-notice-<incident_id> the background feature heal_analysis'): 1,
    ('history', 'incident_id', 'Channel email Recipient …@example.com Incident <incident_id> Attempt # of # Took #.# s Open'): 1,
    ('history', 'incident_id', 'self-healing · policy set by admin job:heal-notice-<incident_id> Kind Every kind The repository'): 1,
    ('history', 'incident_id', 'estimate; nothing was sent By job:heal-notice-<incident_id> Call ai-<hex> About heal_incident'): 1,
}


def _literal(counter) -> str:
    return "\n".join(f"    {k!r}: {n}," for k, n in sorted(counter.items()))


# ── The floor: every surface drawn, reaching the heal records ──────────────────────────────

#: What each surface must hold, so a page that drew nothing, or drew without the records,
#: fails here before the scan is believed.
#: C2817: each record's line in plain words (the mocks' rows), the same on Needs attention and
#: History. C2839: a security ACL is Tier 2, a person's, and this one is not fixed until its
#: removal shape is measured.
CANT_FIX = ("edge-d: “ip access-group EDGE-IN in” was added to interface GigabitEthernet2. "
            "Mercury cannot fix it by itself: it needs a person")
WOULD_HEAL = ("edge-b: “ip route 192.0.2.128 255.255.255.128 192.0.2.10” was added to the global "
              "configuration. Mercury would have put it back itself, but Default is watching "
              "only (dry run), so nothing was sent")
DRAWS = {
    "needs_attention": (CANT_FIX, "Mercury has a fix that restarts OSPF on edge-c: it needs your "
                                  "decision", WOULD_HEAL, "Approve and run on edge-c"),
    "history": (WOULD_HEAL, CANT_FIX),
    "device": (WOULD_HEAL, CANT_FIX),
    "email": ("Mercury: could not fix", "What happened: ", "What Mercury tried:",
              "Open in Mercury:"),
}


def _visible(body, plain):
    if plain:
        return body
    return " ".join(re.sub(r"\s+", " ", t) for t, _s in text_nodes(body))


def test_each_surface_is_drawn_with_the_heal_records(drawn):
    s = _surfaces(drawn)
    assert set(s) == set(SURFACES)
    for surface, bodies in s.items():
        assert bodies, surface
        words = " ".join(_visible(b, p) for _w, b, p in bodies)
        for known in DRAWS[surface]:
            assert known in words, f"{surface} does not draw {known!r}"
        for where, body, plain in bodies:
            assert any(scope for _t, scope in ([(body, True)] if plain else text_nodes(body))), \
                f"{surface}: {where} has no text in scope"
    # The rows a person opens are drawn too: the proposal's card and the can't-fix's analysis.
    slots = [w for w, _b, _p in s["needs_attention"][1:]]
    assert f"/v2/network/Default/heal/proposal/{drawn[':proposal']['id']}" in slots
    assert any(w.startswith("/v2/attention/heal-analysis/Default/hi-") for w in slots)


def test_the_scan_finds_identifiers_on_every_surface(drawn):
    """A floor on the population: each surface whose backlog holds a key is found carrying it,
    and on every surface, Needs attention's among them now that its heal records draw none
    bare (C2817), a bare identifier planted in each body it draws is found, so a scan that
    found none would be blind, not clean."""
    s = _surfaces(drawn)
    got = found(s)
    for surface in {k[0] for k in KNOWN_BARE_IDENTIFIERS}:
        assert any(k[0] == surface for k in got), f"nothing found on {surface}"
    for surface, bodies in s.items():
        for where, body, plain in bodies:
            planted = (body + "\nIncident hi-0123456789ab · planted\n" if plain else
                       body.replace("</body>", "<p>hd-0123456789ab</p></body>", 1)
                       if "</body>" in body else body + "<p>hd-0123456789ab</p>")
            more = sum(found({surface: [(where, planted, plain)]}).values()) - sum(
                found({surface: [(where, body, plain)]}).values())
            assert more == 1, f"{surface}: {where}: a planted identifier found {more} times"


# ── The ratchet ────────────────────────────────────────────────────────────────────────────

def test_no_bare_identifier_outside_the_backlog(drawn):
    got = found(_surfaces(drawn))
    new = Counter({k: n - KNOWN_BARE_IDENTIFIERS.get(k, 0) for k, n in got.items()
                   if n > KNOWN_BARE_IDENTIFIERS.get(k, 0)})
    assert not new, (
        "a bare identifier outside a link or a collapsed 'Details for the record' "
        "(docs/MERCURY_CHARTER.md, 'Human-facing means human-readable', rule 2): link it to its "
        "page or put it under "
        "'Details for the record'; or (kind lookup, rule 5) a person sent to History for what "
        "Mercury already knows: say it in place. New, with how many more than the backlog "
        "allows:\n"
        + _literal(new))


def test_the_backlog_only_holds_what_still_occurs(drawn):
    got = found(_surfaces(drawn))
    gone = {k: n for k, n in KNOWN_BARE_IDENTIFIERS.items() if got.get(k, 0) < n}
    # C2879's measurement: what was found on the same surface and of the same kind that the
    # list does not hold, so a key reshaped (a duration or an age drawn in another form) reads
    # beside the one it was, and a row not drawn at all reads as nothing beside it.
    beside = sorted(k for k in got if k not in KNOWN_BARE_IDENTIFIERS
                    and any(k[:2] == g[:2] for g in gone))
    assert not gone, (
        "fixed, so take them out of KNOWN_BARE_IDENTIFIERS (or lower the count to what is "
        "found): the backlog only shrinks:\n"
        + "\n".join(f"    {k!r}: {n} in the list, {got.get(k, 0)} found"
                    for k, n in sorted(gone.items()))
        + "\nfound on the same surface and of the same kind, not in the list:\n"
        + ("\n".join(f"    {k!r}: {got[k]}" for k in beside) or "    nothing"))


def test_the_backlog_names_only_its_surfaces_and_kinds():
    kinds = {k for k, _rx in PATTERNS} | {"lookup"}
    for (surface, kind, context), n in KNOWN_BARE_IDENTIFIERS.items():
        assert surface in SURFACES and kind in kinds, (surface, kind)
        held = "History" if kind == "lookup" else f"<{kind}>"
        assert held in context and isinstance(n, int) and n > 0, (surface, kind, context)


# ── The planted cases: the scan finds what it must and passes what it must ─────────────────

def test_an_identifier_planted_on_the_real_page_is_found(drawn):
    """A bare decision id planted in the real Needs attention page's main content is one more
    violation, and the same id inside a link or a collapsed "Details for the record" is none."""
    (where, page, _p) = drawn["needs_attention"][0]
    at = page.index("</main>")
    before = found({"needs_attention": [(where, page, False)]})
    for plant, more in (("<p>hd-0123456789ab</p>", 1),
                        ('<p><a href="/v2/history">hd-0123456789ab</a></p>', 0),
                        ("<details><summary>Details for the record</summary>"
                         "<p>hd-0123456789ab</p></details>", 0),
                        ("<details open><summary>Details</summary>"
                         "<p>hd-0123456789ab</p></details>", 1),
                        # Collapsed, but not the record's disclosure: read as shown.
                        ("<details><summary>Details</summary>"
                         "<p>hd-0123456789ab</p></details>", 1)):
        after = found({"needs_attention": [(where, page[:at] + plant + page[at:], False)]})
        assert sum(after.values()) - sum(before.values()) == more, plant


def test_a_lookup_planted_on_the_real_page_is_found(drawn):
    """Rule 5: "find who changed it on History" planted in the real page is one more, in a
    link too; under a collapsed "Details for the record" it is none."""
    (where, page, _p) = drawn["needs_attention"][0]
    at = page.index("</main>")
    before = found({"needs_attention": [(where, page, False)]})
    for plant, more in (("<p>Find who changed it on History.</p>", 1),
                        ('<p>Then <a href="/v2/history">see History</a>.</p>', 1),
                        ("<details><summary>Details for the record</summary>"
                         "<p>Find who changed it on History.</p></details>", 0),
                        ("<details><summary>More</summary>"
                         "<p>Find who changed it on History.</p></details>", 1)):
        after = found({"needs_attention": [(where, page[:at] + plant + page[at:], False)]})
        new = after - before
        assert sum(new.values()) == more and all(k[1] == "lookup" for k in new), plant


@pytest.mark.parametrize("page", [
    "<p>Find who changed it on History.</p>",
    "<p>The change was made outside Mercury: find who changed it on History.</p>",
    "<p>See History</p>",
    "<p>Look on r3's History for the steps.</p>",
    "<p>Look up the change on History</p>",
    "<p>Check History for what verify read.</p>",
    "<p>Decide on it (read the steps on r3's History first)</p>",
    "<p>Read the record on <a href='/v2/device/r3?tab=history'>r3's History</a>, then mark it</p>",
    "<p>Approve it, or see <a href='/v2/history'>History</a>.</p>",
    '<a href="/v2/history">see History</a>',
])
def test_a_lookup_is_found(page):
    assert [k for k, _c in lookups(page)] == ["lookup"], page
    assert [k for k, _c in lookups(_visible(page, False), plain=True)] == ["lookup"], page


def test_a_lookup_starting_its_own_element_is_found():
    """Needs attention's What to do as drawn: the action's link, then the words in their own
    element, with no punctuation between them."""
    page = ("<div><a href='/v2/device/r3'>Open r3</a><span>Read the record on r3's History, "
            "then mark it right or wrong</span></div>")
    assert lookups(page) == [("lookup", "Open r# Read the record on r#'s History, then mark it "
                                        "right or wrong")]


@pytest.mark.parametrize("page", [
    "<p>Open r3's History</p>",
    "<p>Each read and the diagnosis on r3's History</p>",
    "<p>Its record on r3's History</p>",
    "<p>History records what it did</p>",
    "<p>Check drift now on r3</p>",
    "<p>See the card below.</p><p>History</p>",
    "<p>Open in Mercury: /v2/device/r3?tab=history</p>",
    "<details><summary>Details for the record</summary><p>See History</p></details>",
    "<p>Find it.</p><p>It is on History</p>",
])
def test_words_that_send_nobody_to_history_are_not_a_lookup(page):
    assert lookups(page) == [], page

@pytest.mark.parametrize("text,kind", [
    ("incident hi-27a9717bbf09 on edge-d", "incident_id"),
    ("decision hd-5ff79c91db5c recorded", "decision_id"),
    ("Program hash f41455c5f2998f34", "hex"),
    ("commit 487ed33372f0c14d04b3ba74b9d827161d19595c", "hex"),
    ("held by guard 4: its golden departs", "guard"),
    ("Guard 9 holds it", "guard"),
    ("7. decide would_heal: would heal", "step"),
    ("1. claim ok: taken", "step"),
    ("12. record ok", "step"),
])
def test_each_pattern_is_found(text, kind):
    assert [k for k, _c in bare(f"<p>{text}</p>")] == [kind]
    assert [k for k, _c in bare(text, plain=True)] == [kind]


@pytest.mark.parametrize("text", [
    "edge-b would heal in 10 min", "192.0.2.21 and 2001:db8::1", "2026-11-08T19:31:21Z",
    "cost $0.0000", "1. Open the page", "3 hard stops, guards hold", "deadbeef",
    "a 12345678901 count",
])
def test_words_that_are_not_identifiers_are_not_found(text):
    assert bare(f"<p>{text}</p>") == []


@pytest.mark.parametrize("page,count", [
    ("<p>hd-0123456789ab</p>", 1),
    ('<a href="/v2/x">hd-0123456789ab</a>', 0),
    ('<a href="/v2/x"><code>hd-0123456789ab</code></a>', 0),
    ("<a>hd-0123456789ab</a>", 1),                          # not a link: no href
    # The record's disclosure, collapsed: what it holds is out of scope, its summary in.
    ("<details><summary>Details for the record</summary><p>hd-0123456789ab</p></details>", 0),
    ("<details><summary> Details  for the\n record </summary><p>hd-0123456789ab</p></details>",
     0),                                                    # whitespace normalised
    ("<details class='x'><summary><span>Details for the record</span></summary>"
     "<dl><dt>Decision</dt><dd>hd-0123456789ab</dd></dl></details>", 0),
    ("<details><summary>Details for the record</summary><details open><p>hd-0123456789ab</p>"
     "</details></details>", 0),
    ("<details open><details><summary>Details for the record</summary>"
     "<p>hd-0123456789ab</p></details></details>", 0),
    ("<details><summary>Details for the record</summary><a href='/v2/x'>x</a></details>"
     "<p>hd-0123456789ab</p>", 1),                          # after it closes: in scope
    # Open, or named otherwise: read as shown (a History row, a Needs attention row).
    ("<details open><summary>Details for the record</summary><p>hd-0123456789ab</p></details>",
     1),
    ("<details><summary>details for the record</summary><p>hd-0123456789ab</p></details>", 1),
    ("<details><summary>Details for the record, and more</summary><p>hd-0123456789ab</p>"
     "</details>", 1),
    ("<details><summary>Details</summary><p>hd-0123456789ab</p></details>", 1),
    ("<details><p>hd-0123456789ab</p></details>", 1),       # no summary at all
    ("<details><summary>hd-0123456789ab</summary></details>", 1),
    ("<details><summary><a href='/v2/x'>hd-0123456789ab</a></summary></details>", 0),
    ("<details open><p>hd-0123456789ab</p></details>", 1),
    ("<details><summary>Self-healing (dry run): r3</summary><dl><dt>Incident</dt>"
     "<dd>hi-0123456789ab</dd></dl></details>", 1),
    ("<a href='/v2/x'>x</a><p>hd-0123456789ab</p>", 1),
    ("<p>x<br>hd-0123456789ab</p>", 1),
    ("<script>var id = 'hd-0123456789ab';</script>", 0),
    ("<template><p>hd-0123456789ab</p></template>", 0),
    ('<input type="hidden" name="hash" value="f41455c5f2998f34">', 0),
    ("<p title='f41455c5f2998f34'>a hash on hover</p>", 0),
])
def test_the_ancestor_rule(page, count):
    assert len(bare(page)) == count, page


@pytest.mark.parametrize("line,count", [
    ("Incident hi-27a9717bbf09 · sent 2026-11-08T19:58:02Z", 1),
    ("Open in Mercury: /v2/device/edge-d?tab=history&incident=hi-27a9717bbf09", 0),
    ("Open in Mercury: https://mercury.example.com/v2/heal/hd-0123456789ab", 0),
    ("  5. read: edge-d read again (25e2322ce4d52050): ok", 2),
])
def test_in_a_plain_message_only_a_url_carries_an_identifier(line, count):
    assert len(bare(line, plain=True)) == count, line


def test_a_context_says_where_without_the_values_that_move():
    (got,) = bare("<p>Incident hi-27a9717bbf09 · sent 2026-11-08T19:58:02Z</p>")
    assert got == ("incident_id", "Incident <incident_id> · sent #-#-#T#:#:#Z")
    (got,) = bare("<p>Incident hi-0000aaaa1111 · sent 2027-01-01T00:00:00Z</p>")
    assert got == ("incident_id", "Incident <incident_id> · sent #-#-#T#:#:#Z")


def test_a_context_holds_no_age_drawn_from_the_clock():
    """C2948: the same row drawn seconds or minutes after the lab's records is one context;
    CI's runner drew "just now" where the laptop drew "# min ago" (run #1579)."""
    (soon,) = bare("<p>Incident hi-27a9717bbf09 Took 0.4 s just now</p>")
    (later,) = bare("<p>Incident hi-27a9717bbf09 Took 0.4 s 9 min ago</p>")
    assert soon == later == ("incident_id", "Incident <incident_id> Took #.# s # min ago")
