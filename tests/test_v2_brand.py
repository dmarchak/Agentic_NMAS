"""The sidebar's Mercury lockup (NSOT_STAGE7_PLAN section 19, the boards approved 2026-10-05),
and the menu buttons that showed where they do nothing (C475).

The lockup: the mark (the master geometry, its gap in the sidebar's own colour, so the orbit
crosses in front in both themes) beside the short name over the tagline, both read from
`modules.brand`, the one place the name is kept. At phone width, the mark and the short name.

C475 (the operator, 2026-10-05: "the X button next to it doesn't seem to do anything"): the rule
hiding the drawer's close button and the menu button on desktop sat ABOVE `.icon-btn`, whose
`display` won the cascade, so both always showed. On desktop the X closed a drawer that was not
open and the menu button opened one that never moved. The X is gone (the scrim closes the
drawer); the menu button is hidden on desktop and opens the drawer at phone width.
"""

import re

import pytest
from markupsafe import escape as html_escape

from modules import brand
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401


def _sidebar(html):
    return re.search(r'<nav class="sidebar".*?</nav>', html, re.S).group(0)


class TestTheLockup:
    def test_the_sidebar_draws_the_mark_and_the_name_from_one_place(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        head = _sidebar(html)[:2000]
        assert 'class="mercury-mark"' in head and f'aria-label="{brand.PRODUCT_SHORT}"' in head
        assert f'<span class="brand-name">{brand.PRODUCT_SHORT}</span>' in head
        assert f'<span class="brand-sub">{brand.PRODUCT_TAGLINE}</span>' in head
        assert "NMAS" not in head and "brand-mark" not in head

    def test_the_gap_is_the_colour_the_mark_sits_on(self):
        css = open("static/css/nmas-v2.css", encoding="utf-8").read()
        assert re.search(r"^\.mk-gap \{[^}]*stroke: var\(--side\)", css, re.M)
        assert css.count("--brand: #1D9E75;") == 3, "fixed in the light and both dark blocks"

    def test_no_close_button_on_the_drawer(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        assert "Close the menu" not in html and "drawer-close" not in html


class TestTheFiles:
    """Every mark file is what modules/brand.py draws from the master geometry."""

    def test_every_svg_is_what_the_module_draws(self):
        import os
        folder = os.path.join("static", "img", "brand")
        svgs = {f for f in os.listdir(folder) if f.endswith(".svg")}
        assert svgs == set(brand.FILES), "run scripts/nmas-brand-icons"
        for name, draw in brand.FILES.items():
            assert open(os.path.join(folder, name), encoding="utf-8").read() == draw(), name

    def test_the_board_s_simplifications(self):
        """The board (canvas v36): 32 px drops the highlight and the bottom node, keeps the
        gap; 16 px keeps two side nodes and no gap."""
        master, s32, s16 = (brand.mark_parts("#000", "#fff", s) for s in ("master", "32", "16"))
        assert "-4.7,-17.4" in master and 'cy="26" r="9"' in master
        assert "-4.7,-17.4" not in s32 and 'cy="26"' not in s32 and 'stroke-width="12"' in s32
        assert 'stroke-width="12"' not in s16 and s16.count('r="9"') == 2

    def test_the_home_screen_icon_is_the_square_icon_rendered(self):
        width, height, pixel = _png("static/img/brand/apple-touch-icon.png")
        assert (width, height) == (180, 180)
        teal = tuple(int(brand.TEAL[i:i + 2], 16) for i in (1, 3, 5))
        assert pixel(4, 4) == teal, "full-bleed teal: the platform rounds it"
        assert pixel(90, 90) == (255, 255, 255), "the white planet at its centre"


def _png(path):
    """``(width, height, pixel(x, y) -> (r, g, b))`` of an 8-bit RGB or RGBA PNG, read with
    the standard library alone (CI's interpreter has no imaging library)."""
    import struct
    import zlib

    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype, _c, _f, interlace = ihdr
    assert depth == 8 and ctype in (2, 6) and interlace == 0, ihdr
    bpp = 3 if ctype == 2 else 4
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, lambda x, y: tuple(rows[y][x * bpp:x * bpp + 3])


class TestThePages:
    def test_the_head_links_the_icons_and_they_are_served(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        for rel, name in (("icon", "favicon.svg"), ("apple-touch-icon", "apple-touch-icon.png")):
            m = re.search(rf'<link rel="{rel}" href="([^"]*{re.escape(name)}[^"]*)"', html)
            assert m, rel
            assert lab["client"].get(m.group(1)).status_code == 200

    def test_the_phone_top_bar_draws_the_32_px_mark_and_the_short_name(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        bar = re.search(r'<span class="topbar-brand">.*?</span></span>', html, re.S).group(0)
        assert "mercury-mark-small" in bar and "mk-hi" not in bar and 'cy="26"' not in bar
        assert f'<span class="topbar-name">{brand.PRODUCT_SHORT}</span>' in bar

    def test_the_about_page_carries_the_product_card(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/help/about").get_data(as_text=True)
        card = re.search(r'<section class="card product-card" id="product">.*?</section>', html,
                         re.S).group(0)
        for words in (brand.PRODUCT_NAME, brand.PRODUCT_LINE, brand.NAME_ORIGIN.replace("'", "&#39;"),
                      "mercury-icon.svg", "licence: the operator"):
            assert words in card, words
        link = re.search(r'href="([^"]*)">third-party components', card).group(1)
        assert lab["client"].get(link).status_code == 200
        assert html.index('id="product"') < html.index('id="installation"')


#: A word "NMAS" naming the product. A device-side identifier (the NMAS-HEARTBEAT applet) is
#: followed by a hyphen; NMASPROBE is not a word on its own.
PRODUCT_WORD = re.compile(r"\bNMAS\b(?![-_])")


def nmas_shown(html: str) -> list:
    body = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    return PRODUCT_WORD.findall(body)


class TestTheNameLeavesTheScreens:
    """Section 19: "NMAS" leaves the screens and the manual; internal names stay until
    Stage 10. Its population is every argument-free v2 page and a device page, rendered, and
    every manual page; each page's title ends with the short name."""

    def test_a_planted_page_is_found_and_an_identifier_is_not(self):
        assert nmas_shown("<p>NMAS checks it</p>") == ["NMAS"]
        assert nmas_shown("<p>the NMAS-HEARTBEAT applet; NMASPROBE; js/nmas_v2.js</p>") == []

    def test_no_rendered_v2_page_names_nmas(self, lab):  # noqa: F811
        import app as A
        from tests.test_large_fleets import _pages
        from routes.v2 import installation
        pages = [p for p in _pages(A.app) if not p.startswith("/v2/device/")] + ["/v2/device/r3"]
        found, titled = {}, 0
        # About shows the running commit's subject, a record of history: it may name the old
        # product (the commit that removed it does), and is not the screen naming it.
        with A.app.test_request_context("/"):
            subject = installation().get("subject") or ""
        assert subject, "the subject this exclusion is for is read"
        # A host step owed (Needs attention, Update) is a commit's `Host-Step-After:` words,
        # drawn verbatim: the same record of history, never rewritten (CI #540: 44a54ff's step
        # says "the NMAS host"). Each step in the history those pages read is excused as the
        # subject is, and nothing else.
        from modules import host_steps
        recorded = [s["step"] for s in host_steps.steps_in(
            host_steps._log(host_steps.ROOT, "HEAD", host_steps.HISTORY))]
        # The Commit author card (board F3) draws the stored author name as its input's value:
        # the author line of every commit, data like the subject (its default is a KEPT_STRING
        # below), never the screen naming the product. That one attribute is excused.
        from modules.settings_schema import get_setting
        author_value = f'value="{html_escape(get_setting("nsot_git_author_name") or "")}"'
        for path in pages:
            r = lab["client"].get(path)
            if not (r.content_type or "").startswith("text/html"):
                continue
            html = r.get_data(as_text=True)
            for text in [subject] + recorded:
                html = html.replace(str(html_escape(text)), "").replace(text, "")
            html = html.replace(author_value, "")
            if nmas_shown(html):
                found[path] = nmas_shown(html)
            title = re.search(r"<title>(.*?)</title>", html, re.S)
            if title:
                titled += 1
                assert title.group(1).strip().endswith(brand.PRODUCT_SHORT), (path, title.group(1))
        assert titled >= 12, f"the population shrank: {titled} titled pages"
        assert found == {}, found

    def test_no_manual_page_names_nmas_and_each_reads_the_name(self):
        from modules import manual
        assert len(manual.PAGES) >= 39, "the population shrank"
        for slug, *_rest in manual.PAGES:
            html = manual.load(slug)["html"]
            assert not nmas_shown(html), slug
            assert manual.PRODUCT not in html and manual.THIRD_PARTY_LIST not in html, slug
        assert brand.PRODUCT_SHORT in manual.load("getting-started")["html"]


#: The Python strings that still say "NMAS", each with why it is not screen text (section 19:
#: internal names stay until Stage 10 renames them, with their host steps). Exact; only shrinks.
KEPT_STRINGS = {
    ("app.py", "NMAS listening on "): "the console's start-up line, not a screen",
    ("modules/ai_assistant.py", "[SOURCE OF TRUTH"): "the AI agent's prompt (Stage 8)",
    ("modules/config_git.py", "NMAS"): "the git author of the tool's commits, in every history",
    ("modules/settings_schema.py", "NMAS"): "the git author setting's default (the same)",
    ("modules/nsot/repo.py", "NMAS"): "the git author's fallback (the same; two literals)",
    ("modules/nsot/onboard.py", "user.name=NMAS"): "the git author for onboarding's commits",
    ("modules/nsot/bootstrap_config.py", " description NMAS management"):
        "a line written into a device's configuration: renaming it would change every device",
    ("modules/nsot/migrate.py", "the same device held in both stores"):
        "names the legacy golden files' own header text",
}


def screen_strings_naming_nmas(paths=None) -> list:
    """``[(file, text)]``: every non-docstring string literal in app.py, modules/ and routes/
    naming the product "NMAS" as a word, outside KEPT_STRINGS. Parsed, never grepped."""
    import ast
    import os
    import pathlib

    from tests.source_index import tracked

    # Relative to the working directory (the checkout), as KEPT_STRINGS names them.
    paths = paths or [pathlib.Path(os.path.relpath(p))
                      for p in tracked("app.py", "modules", "routes", suffix=".py",
                                       root=".")]
    out = []
    for p in paths:
        if "__pycache__" in p.parts:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        bare = {id(n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in bare
                    and PRODUCT_WORD.search(n.value)):
                rel = p.as_posix()
                if not any(rel == f and n.value.startswith(s) for f, s in KEPT_STRINGS):
                    out.append((rel, n.value[:80]))
    return out


class TestTheNameLeavesTheMessages:
    """A string built in Python reaches a page only in some states (a Needs attention row, a
    refusal, a preview's note), so rendering pages with fixtures cannot find them all: the
    gate's run for this commit found four pages naming "NMAS" that the commit before's run did
    not. So the population is every string literal, parsed."""

    def test_no_screen_string_names_nmas(self):
        assert screen_strings_naming_nmas() == []

    def test_a_planted_string_is_found_and_a_docstring_is_not(self, tmp_path):
        planted = tmp_path / "planted.py"
        planted.write_text('"""NMAS, a docstring."""\nX = "NMAS refused it"\nY = "NMAS_HOST"\n',
                           encoding="utf-8")
        assert [t for _f, t in screen_strings_naming_nmas([planted])] == ["NMAS refused it"]

    def test_every_kept_string_still_exists(self):
        import ast
        import pathlib
        for (f, start), why in KEPT_STRINGS.items():
            tree = ast.parse(pathlib.Path(f).read_text(encoding="utf-8"))
            assert any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and n.value.startswith(start) for n in ast.walk(tree)), (f, start, why)


def test_the_third_party_page_lists_every_component_from_its_inventory():
    import json

    from modules import manual
    import html as html_mod

    doc = json.load(open("docs/THIRD_PARTY.json", encoding="utf-8"))
    html = html_mod.unescape(manual.load("third-party")["html"])
    for entry in doc["vendored"].values():
        assert f"<strong>{entry['component']}</strong> {entry['version']}" in html, \
            entry["component"]
    for name, entry in doc["python"].items():
        assert f"<strong>{name}</strong> {entry['version']}: {entry['licence']}" in html, name
    assert html.count("<li>") == len(doc["vendored"]) + len(doc["python"])


def _shown(b, sel):
    return b.js("var e = document.querySelector(arguments[0]);"
                "return !!e && getComputedStyle(e).display !== 'none'", sel)


def test_the_menu_button_shows_only_where_it_opens_the_drawer(served):  # noqa: F811
    srv, b = served
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 800})
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    assert not _shown(b, ".menu-btn"), "on desktop the menu button opens nothing"
    assert _shown(b, ".brand-sub") and not _shown(b, ".topbar-brand")
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 800})
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    assert _shown(b, ".menu-btn") and not _shown(b, ".brand-sub") and _shown(b, ".topbar-brand")
    b.click(".menu-btn")
    b.wait_for("return !!document.querySelector('.sidebar.open')", 5)
    b.js("document.querySelector('.scrim').click(); return 1")
    b.wait_for("return !document.querySelector('.sidebar.open')", 5)


def test_the_about_card_puts_the_icon_beside_the_words(served):  # noqa: F811
    """Board B: the icon beside the name, not above it (`.card`, set later in the stylesheet,
    made it a column until `.card.product-card` outranked it, C475's kind of cascade)."""
    srv, b = served
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 800})
    b.go(srv.url("/v2/help/about"))
    b.wait_for(READY, 15)
    assert b.js("return getComputedStyle(document.getElementById('product')).flexDirection") == "row"
    icon, words = b.js("var r = function (s) { return document.querySelector(s)"
                       ".getBoundingClientRect(); };"
                       "return [r('.product-icon').right, r('.product-words').left]")
    assert icon <= words, "the words sit to the right of the icon"
