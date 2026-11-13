"""The Help pages' text takes the full width, and a diagram is in the flow of the text (the
operator, 2026-11-13: "the Help pages' text full width with the diagram above or in line").

Measured before, in a real browser at 1280 px on Deploy a change (`/v2/help/deploy`): `<main>`
1020 px wide (956 inside its padding), Help's page list 220 px, the article 716 px; the page's
diagram in a 440 px column of its own beside the text, sticky, which left the text 248 px:
24% of the main area. A page with no diagram drew its text 716 px wide, held to 760 px on a
wider screen.

- **The renderer:** `manual.render`'s *page* is the page's blocks in the file's order, the lead
  diagram in its place and marked `diagram-lead`; without that block it is *html*, the text
  the side panel draws after the diagram.
- **Every declared page:** no column wrapper and no `aside` in the article; a page with a lead
  diagram draws it once, a child of the article like its paragraphs, before its first section.
- **In a real browser, at 1280 and at 1920 px:** every block of the text is as wide as the
  article, which with Help's page list and the gap between them is the whole width `<main>`
  gives (so the text is all of the main area beside the page list, never under 90% of it);
  each diagram starts at the text's left edge and no block of the text is beside it.
"""

import re

import pytest

from modules import manual
from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401

#: The article of a rendered Help page.
ARTICLE = re.compile(r'<article class="help-body manual">(.*?)</article>', re.S)
#: A lead diagram as the page draws it.
LEAD = '<figure class="diagram diagram-lead">'


def _client():
    import app as A
    return A.app.test_client()


class TestTheRenderer:
    TEXT = ("# T\n\nThe opening words.\n\n![What it shows, in words long enough.]"
            "(diagrams/deploy.svg)\n\nMore before a section.\n\n## One\n\ntext\n\n"
            "![Another, inside a section.](diagrams/drift.svg)\n")

    def test_the_page_draws_the_lead_diagram_where_its_file_places_it(self):
        doc = manual.render(self.TEXT)
        page = doc["page"]
        assert page.count(LEAD) == 1 and doc["lead"].startswith('<figure class="diagram">')
        assert page.index("The opening words.") < page.index(LEAD) \
            < page.index("More before a section.") < page.index('<h2 id="one">')
        # A diagram inside a section is drawn as it was, in the flow, and is no lead.
        assert page.count('<figure class="diagram">') == 1 == doc["html"].count("<figure")

    def test_without_the_lead_the_page_is_the_panel_s_text(self):
        doc = manual.render(self.TEXT)
        marked = doc["lead"].replace('<figure class="diagram">', LEAD, 1)
        assert marked in doc["page"] and doc["lead"] not in doc["html"]
        assert doc["page"].replace(marked + "\n", "", 1) == doc["html"]

    def test_a_page_with_no_diagram_is_its_text(self):
        doc = manual.render("# T\n\nwords\n\n## One\n\ntext\n")
        assert doc["page"] == doc["html"] and not doc["lead"]


class TestEveryPage:
    def test_no_page_draws_a_column_beside_its_text(self):
        slugs = [s for s, _t, _g, _f in manual.PAGES]
        assert len(slugs) >= 60, "the population: every declared manual page"
        client, with_lead = _client(), 0
        for slug in slugs:
            r = client.get(f"/v2/help/{slug}")
            assert r.status_code == 200, slug
            found = ARTICLE.search(r.get_data(as_text=True))
            assert found, f"{slug}: its article is not drawn as the page's own block"
            article = found.group(1)
            assert "<aside" not in article and "manual-cols" not in article, slug
            assert 'class="manual-' not in article.replace('class="manual-title"', ""), slug
            doc = manual.load(slug)
            assert article.count(LEAD) == (1 if doc["lead"] else 0), slug
            if doc["lead"]:
                with_lead += 1
                first_section = re.search(r'<h2 id="', article)
                assert first_section is None or article.index(LEAD) < first_section.start(), slug
        assert with_lead >= 23, "the pages a lead diagram is drawn on (How it works, Concepts)"


#: What the page drew: `<main>`'s width inside its padding, Help's page list, the gap between
#: it and the article, the article, each block of the article (its direct children) and each
#: diagram's drawing.
DRAWN = """
function box(e) { var b = e.getBoundingClientRect();
  return {tag: e.tagName.toLowerCase(), cls: e.className && e.className.baseVal === undefined
            ? e.className : '', x: b.left, y: b.top, w: b.width, h: b.height,
          position: getComputedStyle(e).position, float: getComputedStyle(e).cssFloat}; }
var main = document.querySelector('main'), cs = getComputedStyle(main);
var grid = document.querySelector('.help-grid'), article = document.querySelector('.help-body');
return {inner: window.innerWidth,
        main: main.getBoundingClientRect().width,
        mainInside: main.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
        gap: parseFloat(getComputedStyle(grid).columnGap),
        list: box(document.querySelector('.helpnav')), article: box(article),
        blocks: Array.prototype.map.call(article.children, box),
        drawings: Array.prototype.map.call(article.querySelectorAll('figure.diagram svg'), box),
        wide: document.documentElement.scrollWidth - document.documentElement.clientWidth};
"""

#: A page with a tall lead diagram, a Concepts page, a Screens page that draws none, and the
#: longest How it works page: (slug, whether it draws a diagram).
PAGES = (("deploy", True), ("drift", True), ("devices", False), ("heal", True))


def _beside(a, b) -> bool:
    """Whether boxes *a* and *b* share any height (so one is beside the other, not above)."""
    return a["y"] < b["y"] + b["h"] - 0.5 and b["y"] < a["y"] + a["h"] - 0.5


@pytest.mark.parametrize("width", [1280, 1920])
def test_the_text_is_full_width_and_no_diagram_is_beside_it(served, width):  # noqa: F811
    srv, b = served
    b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
    for slug, draws in PAGES:
        b.go(srv.url(f"/v2/help/{slug}"))
        b.wait_for(READY, 20)
        d = b.js(DRAWN)
        assert d["inner"] == width and d["wide"] <= 0, (slug, d["inner"], d["wide"])
        article, blocks = d["article"], d["blocks"]
        text = [x for x in blocks if x["tag"] in ("p", "ul", "ol", "h2", "h3", "pre")]
        figures = [x for x in blocks if x["tag"] == "figure"]
        assert len(text) >= 8, (slug, "the population: the article's own blocks", len(text))
        assert len(text) + len(figures) == len(blocks), \
            (slug, "a wrapper in the article", [x["tag"] for x in blocks])
        assert bool(figures) == draws and len(d["drawings"]) == len(figures), slug
        # The main area: what <main> gives the page beside Help's own page list.
        area = d["mainInside"] - d["list"]["w"] - d["gap"]
        assert abs(article["w"] - area) <= 1, (slug, width, article["w"], area)
        assert area >= 0.7 * d["mainInside"], (slug, "the page list took the page", area)
        for x in text + figures:
            assert x["w"] >= 0.9 * area and abs(x["w"] - article["w"]) <= 1, \
                (slug, width, x["tag"], x["w"], "of the main area's", area)
            assert x["float"] == "none" and x["position"] == "static", (slug, x)
        for fig, drawing in zip(figures, d["drawings"]):
            assert abs(drawing["x"] - article["x"]) <= 1, (slug, "the diagram's left", drawing)
            beside = [x["tag"] for x in text if _beside(x, drawing)]
            assert not beside, (slug, width, "text beside the diagram", beside)
            assert fig["y"] > text[0]["y"], (slug, "the diagram is in the flow, after the title")
