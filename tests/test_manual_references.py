"""What a manual page names must exist in v2 (K33, the operator, 2026-10-19: "every screen, control
and route a page names must resolve to a real v2 template or route ... and every how() slug must
be reachable from its screen").

Mechanised here, each with a planted dead reference:
- **A route:** every ``/v2/...`` path a page names is a route the app serves (a ``<name>`` in the
  page stands for any one path segment).
- **A dialog's control:** every bold label ending in "…" (the interface's mark for a control that
  opens a preview or a form, NSOT_GUI_BRIEF) is drawn, word for word, by a v2 template, a v2
  script, or the code that builds a v2 card's words.
- **Reachable:** every How it works page is opened by a "How does this work?" link (``how()``) or
  an info link (``info()``) on some v2 screen.

Already mechanised elsewhere (tests/test_manual.py): every info and how link names a page and
section that exist; every sidebar destination and device tab has its page; every declared step of
every operation is named on its page; every action carries its link.

**Not mechanised** (the claims a reviewer reads against the code): a screen named in a breadcrumb
("Credentials › Profiles"), a bold control label without the "…", a status word, a default, a
limit or number, and what a step reads, sends and records.
"""

import os
import re

from modules import manual
from tests import source_index

#: A v2 path as a page writes it: `/v2/...`, segments of path characters or `<placeholder>`s.
ROUTE = re.compile(r"(?<![\w/])/v2(?:/(?:<[a-z_]+>|[A-Za-z0-9_.-]+))*/?")
#: A bold label ending in "…": a control that opens a preview or a form.
DIALOG = re.compile(r"\*\*([^*\n]{2,60}…)\*\*")


def manual_texts() -> dict:
    """``{slug: markdown}`` for every declared page."""
    out = {}
    for slug, _title, _group, rel in manual.PAGES:
        with open(os.path.join(manual.MANUAL_DIR, rel), encoding="utf-8") as fh:
            out[slug] = fh.read()
    return out


def route_patterns(rules) -> list:
    """Each served v2 rule as a regex over a path whose `<placeholder>`s are one segment."""
    out = []
    for rule in rules:
        if not rule.startswith("/v2"):
            continue
        parts = re.split(r"(<[^>]+>)", rule)
        out.append(re.compile("".join("[^/]+" if p.startswith("<") else re.escape(p)
                                      for p in parts)))
    return out


def dead_routes(texts: dict, patterns: list) -> list:
    """``(slug, path)`` for each path a page names that no served rule matches. A path ending in
    "/" names what is under it, and resolves when some rule continues it."""
    bad = []
    for slug, text in sorted(texts.items()):
        for path in sorted({p.rstrip(".") for p in ROUTE.findall(text)}):
            probe = re.sub(r"<[a-z_]+>", "x1", path)
            if any(p.fullmatch(probe) or p.fullmatch(probe.rstrip("/")) for p in patterns):
                continue
            if probe.endswith("/") and any(p.pattern.startswith(re.escape(probe)) or
                                           p.match(probe) for p in patterns):
                continue
            bad.append((slug, path))
    return bad


def drawn_words() -> str:
    """Every v2 template, v2 script and the Python that builds a card's words, as one text."""
    files = (source_index.tracked("templates/v2", suffix=".html", recursive=False) +
             [f for f in source_index.tracked("static/js", suffix=".js", recursive=False)
              if os.path.basename(f).startswith("nmas_")] +
             source_index.tracked("routes", suffix=".py", recursive=False) +
             source_index.tracked("modules", suffix=".py"))
    out = []
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        out.append(visible(text) if f.endswith(".html") else text)
    return "\n".join(out)


def visible(html: str) -> str:
    """A template's words as a person reads them: `Save <span x-text="count">({{ n }})</span>…`
    is "Save ({{ n }})…"."""
    return re.sub(r"<[^>{}]+>", "", html)


def label_pattern(label: str):
    """A control's label as a page writes it, as a regex over the code that draws it: the last
    segment of a path ("Actions › Save…" is the menu's "Save…"), and each ``<placeholder>`` the
    page writes for a value the template fills (``{{ ... }}``)."""
    last = re.split(r" › | > ", label)[-1]
    parts = re.split(r"<[^>]+>", last)
    return re.compile(r"\{\{[^}]*\}\}".join(re.escape(p) for p in parts))


def dead_controls(texts: dict, drawn: str) -> list:
    """``(slug, label)`` for each dialog control a page names that nothing in v2 draws."""
    return [(slug, label) for slug, text in sorted(texts.items())
            for label in sorted(set(DIALOG.findall(text)))
            if not label_pattern(label).search(drawn)]


def linked_slugs(templates_text: str) -> set:
    return set(re.findall(r"\b(?:how|info)\(\s*'([a-z0-9-]+)'", templates_text))


def unreachable(pages, linked: set) -> list:
    """The How it works pages no v2 screen links to."""
    return [slug for slug, _t, group, _r in pages if group == manual.H and slug not in linked]


def _app_rules():
    import app as A
    return [r.rule for r in A.app.url_map.iter_rules()]


def _templates_text():
    out = []
    for f in source_index.tracked("templates/v2", suffix=".html", recursive=False):
        with open(f, encoding="utf-8") as fh:
            out.append(fh.read())
    return "\n".join(out)


class TestEveryReferenceResolves:
    def test_the_population(self):
        texts = manual_texts()
        assert len(texts) >= 58
        assert sum(len(ROUTE.findall(t)) for t in texts.values()) >= 15
        assert sum(len(DIALOG.findall(t)) for t in texts.values()) >= 40

    def test_every_route_a_page_names_is_served(self):
        assert dead_routes(manual_texts(), route_patterns(_app_rules())) == []

    def test_every_dialog_control_a_page_names_is_drawn(self):
        assert dead_controls(manual_texts(), drawn_words()) == []

    def test_every_how_it_works_page_is_reachable_from_a_screen(self):
        assert unreachable(manual.PAGES, linked_slugs(_templates_text())) == []


class TestTheCheckCanFail:
    def test_a_dead_route_is_found_and_a_served_one_is_not(self):
        patterns = route_patterns(["/v2/device/<name>", "/v2/device/<name>/rotate/<job>",
                                   "/v2/history", "/static/<path:f>"])
        texts = {"p": "Open /v2/device/<name>, then /v2/history. See /v2/nowhere and "
                      "/v2/device/<name>/rotate/ and /v2/device/<name>/gone."}
        assert dead_routes(texts, patterns) == [("p", "/v2/device/<name>/gone"),
                                                ("p", "/v2/nowhere")]

    def test_a_dead_control_is_found_and_a_drawn_one_is_not(self):
        texts = {"p": "Press **Move to the database…**, then **Frobnicate…**, then **Save**, "
                      "then **Actions › Save every device of <network> (<count>)…**, then "
                      "**Save every device of the network…**."}
        drawn = ('<button>Move to the database…</button>'
                 '<a>Save every device of {{ d.list }} ({{ d.managed }})…</a>')
        assert dead_controls(texts, drawn) == [("p", "Frobnicate…"),
                                               ("p", "Save every device of the network…")]

    def test_a_label_split_by_markup_is_read_as_a_person_reads_it(self):
        texts = {"p": "Choose **Actions › Save (<count>)…**."}
        drawn = '<button><span>Save <span x-text="count">({{ picked | length }})</span>…</span>'
        assert dead_controls(texts, drawn) == [("p", "Actions › Save (<count>)…")]
        assert dead_controls(texts, visible(drawn)) == []

    def test_an_unlinked_page_is_found(self):
        pages = (("deploy", "t", manual.H, "f"), ("orphan", "t", manual.H, "f"),
                 ("devices", "t", "Screens", "f"))
        assert unreachable(pages, linked_slugs("{{ how('deploy') }}")) == ["orphan"]
