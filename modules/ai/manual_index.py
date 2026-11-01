"""ai/manual_index.py — the manual's sections, chosen for a question by code (card P7, the toolbar
assistant, stage 1; board P7's approved question on grounding, 2026-11-01: the manual is about
190,000 to 230,000 tokens, far too big to send whole, so a how-to answer is grounded in the few
sections a deterministic index chooses, never the whole manual and never a model's choice).

`sections` reads every declared page (`modules.manual.PAGES`, through `manual.source`, so the
product's name is filled in) and splits it at its ``##`` and ``###`` headings: each section is
its page, its anchor (the heading's ``{#id}``, or `manual.anchor_of` of its words, as the Help
page renders it) and its words. A page's lead (before its first heading) is a section with no
anchor. Diagrams are left out: their words are the alt text, kept beside the text already.

`select` scores each section against the question's words: each word's weight is how rare it
is across the sections (an inverse document frequency), counted in the section's text (each
count damped) and three times in its heading; the page of the screen the person is on, when
given (`manual.SCREENS`), scores more. The best sections are returned within a character
budget, each with its link; a question nothing scores is ``[]``, a manual gap the caller says
and records (P7: "Where the manual does not cover the question, it says so").
"""
import math
import re

#: Words too common to tell sections apart.
STOP = frozenset("""a an and are as at be by can do does for from has have how i if in into is it
its my no not of on or so that the their then there these this to was what when where which who
why will with you your does doing done mercury""".split())
#: A section's text counts once; its heading counts this many times more.
HEADING_WEIGHT = 3.0
#: The score added to a section on the page of the screen the person is on.
SCREEN_BOOST = 2.0
#: Sections returned at most, and the characters they may hold in all.
LIMIT = 4
BUDGET_CHARS = 12000

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


def _idf(all_sections: list) -> dict:
    if "idf" in _CACHE:
        return _CACHE["idf"]
    n = len(all_sections)
    df = {}
    for s in all_sections:
        for w in set(words(s["heading"] + " " + s["text"])):
            df[w] = df.get(w, 0) + 1
    _CACHE["idf"] = {w: math.log(1 + n / d) for w, d in df.items()}
    return _CACHE["idf"]


def select(question: str, screen: str = "", limit: int = LIMIT,
           budget: int = BUDGET_CHARS) -> list:
    """The sections that best answer *question*, at most *limit* and *budget* characters in all,
    each ``{"slug", "page", "anchor", "heading", "text", "link", "score"}``, the best first;
    ``[]`` when no section shares a telling word with it. *screen* is the screen the person is
    on, as `manual.SCREENS` names it."""
    from modules import manual

    asked = set(words(question))
    if not asked:
        return []
    all_s = sections()
    idf = _idf(all_s)
    page_of_screen = manual.SCREENS.get(screen or "", "")
    scored = []
    for i, s in enumerate(all_s):
        body = words(s["text"])
        head = words(s["heading"])
        score = 0.0
        for w in asked:
            tf = body.count(w)
            if tf:
                score += idf.get(w, 0) * (1 + math.log(tf))
            if w in head:
                score += idf.get(w, 0) * HEADING_WEIGHT
        if score <= 0:
            continue
        if page_of_screen and s["slug"] == page_of_screen:
            score += SCREEN_BOOST
        scored.append((-score, i, s))
    out, used = [], 0
    for neg, _i, s in sorted(scored):
        if len(out) >= limit or used + len(s["text"]) > budget:
            continue
        out.append(dict(s, score=round(-neg, 3)))
        used += len(s["text"])
    return out


def size() -> dict:
    """``{"pages", "sections", "chars"}``: the index's size, for the card's measured basis."""
    all_s = sections()
    return {"pages": len({s["slug"] for s in all_s}), "sections": len(all_s),
            "chars": sum(len(s["text"]) for s in all_s)}
