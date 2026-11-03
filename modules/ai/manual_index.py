"""ai/manual_index.py — the manual's sections, chosen for a question by code (card P7, the toolbar
assistant, stage 1; board P7's approved question on grounding, 2026-11-01: the manual is about
190,000 to 230,000 tokens, far too big to send whole, so a how-to answer is grounded in the few
sections a deterministic index chooses, never the whole manual and never a model's choice).

`sections` reads every declared page (`modules.manual.PAGES`, through `manual.source`, so the
product's name is filled in) and splits it at its ``##`` and ``###`` headings: each section is
its page, its anchor (the heading's ``{#id}``, or `manual.anchor_of` of its words, as the Help
page renders it) and its words. A page's lead (before its first heading) is a section with no
anchor. Diagrams are left out: their words are the alt text, kept beside the text already.

**Stage 1's retriever (the operator's order of 2026-11-02; fully offline, no embedding
model).** `passages` indexes each section whole, or a long one split at its paragraphs (5 to 8
must fit 3 to 5k tokens, and the longest section is about 17,000 characters), each keeping
its section's link. `ranked` scores them by BM25 (`K1`, `B`) over each passage's words, a
heading's words `HEADING_WEIGHT` more; the question's words, each plural's ``s`` dropped
(`stem`), with the manual's words for what people call otherwise (`ALIASES`, a maintained list:
host key, re-key; password, secret reference; reboot, reload); and the page of the screen the
person asks from `SCREEN_BOOST` more. `select` sends the best, at most `LIMIT` within
`BUDGET_CHARS`, and never pads: below `COVERED_SCORE`, or when the best meets less than `COVER`
of the question's words, it is ``[]``, a manual gap the caller answers "the manual doesn't cover
this" and records; a passage under `PAD_SHARE` of the best is left out. `evaluate` measures
retrieval alone, recall@k over recorded cases naming their expected sections, so a wrong answer
says whether the retriever or the model failed.
"""
import collections
import math
import re

#: Words too common to tell sections apart.
STOP = frozenset("""a an and are as at be by can do does for from has have how i if in into is it
its my no not of on or so that the their then there these this to was what when where which who
why will with you your does doing done mercury about""".split())
#: A term in a section's heading adds this many times its weight beyond its BM25 in the text.
HEADING_WEIGHT = 3.0
#: The score added to a passage on the page of the screen the person is on.
SCREEN_BOOST = 2.0
#: BM25's term saturation and length normalisation, the method's usual values (not tuned).
K1, B = 1.2, 0.75
#: Passages returned at most, and the characters they may hold in all: within the operator's 3
#: to 5k tokens (2026-11-02) at either rate on record, about 3,000 tokens at 4 characters a
#: token and about 4,600 at the 2.585 C1798 states (no call has measured the manual's own; the
#: first run's provider count does); a long section is split into passages of at most
#: PASSAGE_CHARS so 5 to 8 fit.
LIMIT = 8
BUDGET_CHARS = 12000
PASSAGE_CHARS = 1800
#: The gap rules (`select`), calibrated on the recorded retrieval cases
#: (tests/fixtures/manual_retrieval/cases.json, `evaluate`): the share of the question's
#: own words the best passage must meet, the best's least score, and the share of the best's
#: score a further passage must reach to be sent rather than pad.
COVER = 0.25
COVERED_SCORE = 9.0
PAD_SHARE = 0.35
#: The words people ask in and the manual's for the same thing (the operator's order of
#: 2026-11-02: a maintained list). Each phrase found in a question adds the manual's words;
#: add a pair when a recorded case or a logged manual gap shows the manual says it otherwise.
ALIASES = {
    "host key": ["re-key", "rekey"], "ssh key": ["re-key", "rekey"],
    "fingerprint": ["re-key", "host key"],
    "password": ["secret reference", "credential", "rotate"],
    "reboot": ["reload"], "restart": ["reload"], "power cycle": ["reload"],
    "push": ["deploy"], "apply": ["deploy"],
    "running config": ["capture", "running-config"], "copy": ["capture"],
    "write memory": ["save", "startup"], "startup": ["save"],
    "undo": ["revert"], "roll back": ["revert", "rollback"], "try again": ["retry"],
    "out of service": ["retire"], "decommission": ["retire"],
    "add a": ["onboard"], "new switch": ["onboard"], "new router": ["onboard"],
    "known good": ["restore", "baseline"],
    "delete a line": ["removal", "mode b"], "remove a line": ["removal", "mode b"],
    "fixed address": ["reservation"], "static address": ["reservation"],
    "go away": ["clears", "acknowledge"], "dismiss": ["acknowledge", "clears"],
    "last week": ["history"], "past": ["history"],
    "upgrade": ["update"], "new version": ["update"],
    "by hand": ["edit"],
    "many devices": ["fleet", "layer", "ticked"], "all routers": ["fleet", "layer"],
    "ten devices": ["fleet", "layer", "ticked"],
}

_HEAD = re.compile(r"^(#{2,3}) (.+?)(?: \{#([a-z0-9-]+)\})?\s*$")
_DIAGRAM = re.compile(r"^!\[[^\]]*\]\(diagrams/[a-z0-9-]+\.svg\)\s*$")
_WORD = re.compile(r"[a-z0-9][a-z0-9_-]*")

_CACHE = {}


def words(text: str) -> list:
    """The words of *text* that can tell sections apart: lower case, at least three
    characters, not in `STOP`."""
    return [w for w in _WORD.findall((text or "").lower()) if len(w) >= 3 and w not in STOP]


def sections() -> list:
    """Every section of every declared page: ``{"slug", "page", "anchor", "heading", "text",
    "link"}``, in the manual's order; read once a process."""
    if "sections" in _CACHE:
        return _CACHE["sections"]
    from modules import manual

    out = []
    for slug, title, _group, _rel in manual.PAGES:
        try:
            text = manual.source(slug)
        except (OSError, manual.ManualError):
            continue
        cur = {"slug": slug, "page": title, "anchor": "", "heading": title, "lines": []}
        for line in text.splitlines():
            m = _HEAD.match(line)
            if m:
                out.append(cur)
                cur = {"slug": slug, "page": title,
                       "anchor": m.group(3) or manual.anchor_of(m.group(2)),
                       "heading": m.group(2), "lines": []}
                continue
            if line.startswith("# ") or _DIAGRAM.match(line):
                continue
            cur["lines"].append(line)
        out.append(cur)
    result = []
    for s in out:
        body = "\n".join(s.pop("lines")).strip()
        if not body:
            continue
        s["text"] = body
        s["link"] = f"/v2/help/{s['slug']}" + (f"#{s['anchor']}" if s["anchor"] else "")
        result.append(s)
    _CACHE["sections"] = result
    return result


def stem(word: str) -> str:
    """A word's one normalisation: a plural's ``s`` dropped (``alerts`` is ``alert``), so the
    question's form and the manual's meet."""
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def terms(text: str) -> list:
    """`words`, each `stem`med: what is indexed and what is asked."""
    return [stem(w) for w in words(text)]


def passages() -> list:
    """Every section as the retriever indexes it: a section of at most `PASSAGE_CHARS` whole,
    a longer one split at its paragraphs into passages of at most that (a paragraph longer than
    it at its lines; one line longer than it is its own passage), each keeping its section's slug, anchor, heading and link, so 5 to 8 fit
    the question's budget; with each passage's terms and length, read once a process."""
    if "passages" in _CACHE:
        return _CACHE["passages"]
    out = []
    for s in sections():
        # Paragraphs, and a paragraph longer than a passage (a long list) at its lines.
        units = []
        for para in re.split(r"\n\s*\n", s["text"]):
            if len(para) <= PASSAGE_CHARS:
                units.append(("\n\n", para))
            else:
                units += [("\n\n" if i == 0 else "\n", line)
                          for i, line in enumerate(para.split("\n"))]
        parts, cur = [], ""
        for sep, unit in units:
            if cur and len(cur) + len(sep) + len(unit) > PASSAGE_CHARS:
                parts.append(cur)
                cur = unit
            else:
                cur = f"{cur}{sep}{unit}" if cur else unit
        parts.append(cur)
        for i, text in enumerate(parts):
            body = terms(text)
            out.append(dict(s, text=text, part=i, parts=len(parts),
                            _body=collections.Counter(body), _len=len(body),
                            _head=set(terms(s["heading"]))))
    _CACHE["passages"] = out
    return out


def _idf(all_p: list) -> dict:
    """BM25's inverse document frequency over the passages, each term's ``ln(1 + (N - df +
    0.5) / (df + 0.5))``, and ``None``'s the value for a term no passage holds."""
    if "idf" in _CACHE:
        return _CACHE["idf"]
    n = len(all_p)
    df = collections.Counter()
    for p in all_p:
        df.update(set(p["_body"]) | p["_head"])
    idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
    idf[None] = math.log(1 + (n + 0.5) / 0.5)
    _CACHE["idf"] = idf
    return idf


def asked(question: str) -> list:
    """The question's terms, each ``(term, its words)``: its own words, then each `ALIASES`
    phrase it holds expanded into the manual's words, each credited to the phrase's words (for
    `COVER`)."""
    q = (question or "").lower()
    out = [(w, {w}) for w in dict.fromkeys(terms(q))]
    for phrase, said in ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", q):
            own = set(terms(phrase))
            out += [(t, own) for a in said for t in terms(a) if t not in {x for x, _ in out}]
    return out


def _bm25(p: dict, term: str, idf: float, avg: float) -> float:
    tf = p["_body"].get(term, 0)
    body = (idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * p["_len"] / avg))) if tf else 0.0
    return body + (idf * HEADING_WEIGHT if term in p["_head"] else 0.0)


def ranked(question: str, screen: str = "") -> dict:
    """Every passage that scores for *question*, the best first, each with its ``score``, and
    ``cover``, the share of the question's own words (by their weight) the best passage meets,
    directly or through an alias: ``{"passages", "cover"}``. *screen* is the screen the person
    is on (`manual.SCREENS`' name, or a page's slug): its page's passages score `SCREEN_BOOST`
    more."""
    from modules import manual

    want = asked(question)
    if not want:
        return {"passages": [], "cover": 0.0}
    all_p = passages()
    idf = _idf(all_p)
    avg = sum(p["_len"] for p in all_p) / len(all_p)
    page = manual.SCREENS.get(screen or "", "") or (
        screen if any(p["slug"] == screen for p in all_p) else "")
    own = {w: idf.get(w, idf[None]) for w, _src in want if _src == {w}}
    scored = []
    for i, p in enumerate(all_p):
        score, met = 0.0, set()
        for term, src in want:
            got = _bm25(p, term, idf.get(term, 0.0), avg)
            if got:
                score += got
                met |= src
        if score <= 0:
            continue
        if page and p["slug"] == page:
            score += SCREEN_BOOST
        scored.append((-score, i, p, met))
    scored.sort(key=lambda x: (x[0], x[1]))
    total = sum(own.values()) or 1.0
    cover = (sum(v for w, v in own.items() if w in scored[0][3]) / total) if scored else 0.0
    return {"passages": [dict({k: v for k, v in p.items() if not k.startswith("_")},
                              score=round(-neg, 3)) for neg, _i, p, _m in scored],
            "cover": round(cover, 3)}


def select(question: str, screen: str = "", limit: int = LIMIT,
           budget: int = BUDGET_CHARS) -> list:
    """The passages that answer *question*, at most *limit* and *budget* characters in all, each
    ``{"slug", "page", "anchor", "heading", "text", "link", "part", "parts", "score"}``, the
    best first. ``[]`` is a manual gap, said and recorded by the caller (`record_gap`), never
    padded: when no passage scores, when the best one meets less than `COVER` of the question's
    own words (it asks what the manual never speaks of), or when the best scores under
    `COVERED_SCORE`; and a passage under `PAD_SHARE` of the best is weaker padding, left
    out. *screen* as `ranked`."""
    got = ranked(question, screen)
    top = got["passages"][0]["score"] if got["passages"] else 0.0
    if not got["passages"] or got["cover"] < COVER or top < COVERED_SCORE:
        return []
    out, used = [], 0
    for p in got["passages"]:
        if len(out) >= limit or p["score"] < top * PAD_SHARE:
            break
        if used + len(p["text"]) > budget:
            continue
        out.append(p)
        used += len(p["text"])
    return out


def hits(expect: list, got: list) -> bool:
    """Whether *got* (sections) holds one *expect* names: ``slug#anchor`` exactly, or ``slug``
    for any section of that page."""
    have = {(s["slug"], s["anchor"]) for s in got}
    for e in expect:
        slug, _, anchor = e.partition("#")
        if ("#" in e and (slug, anchor) in have) or ("#" not in e and
                                                      any(h[0] == slug for h in have)):
            return True
    return False


def evaluate(cases: list, k: int = 5, choose=None) -> dict:
    """Retrieval alone, apart from any answer (the operator, 2026-11-02): over recorded *cases*
    (``{"n", "q", "screen", "expect"}``), ``recall`` the share of covered cases (an expect
    naming a section) whose top *k* sections hold one it names, and ``gaps`` the share of
    uncovered ones (an empty expect) answered with no section; each case's ``misses``.
    *choose* replaces `select` (tests)."""
    choose = choose or select
    covered, uncovered, misses = 0, 0, []
    found = gapped = 0
    for c in cases:
        got = choose(c["q"], screen=c.get("screen") or "")[:k]
        if c["expect"]:
            covered += 1
            if hits(c["expect"], got):
                found += 1
            else:
                misses.append({"n": c["n"], "q": c["q"], "expect": c["expect"],
                               "got": [f"{s['slug']}#{s['anchor']}" for s in got]})
        else:
            uncovered += 1
            if not got:
                gapped += 1
            else:
                misses.append({"n": c["n"], "q": c["q"], "expect": [],
                               "got": [f"{s['slug']}#{s['anchor']}" for s in got]})
    return {"recall": found / covered if covered else 0.0, "covered": covered, "found": found,
            "gaps": gapped / uncovered if uncovered else 0.0, "uncovered": uncovered,
            "gapped": gapped, "k": k, "misses": misses}


def size() -> dict:
    """``{"pages", "sections", "chars"}``: the index's size, for the card's measured basis."""
    all_s = sections()
    return {"pages": len({s["slug"] for s in all_s}), "sections": len(all_s),
            "chars": sum(len(s["text"]) for s in all_s)}
