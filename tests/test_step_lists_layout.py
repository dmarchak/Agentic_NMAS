"""C1115 and C1116 (the operator, W3, 2026-10-17): a step list (`ol.set-steps`) is a grid per
row, a 76 px badge column then the text, so a list of plain lines (NetBox's import plan, the
Remove and Stop tracking plans: `preview_parts`' program) drew each line one word wide in the
badge column, and a badge wider than the column ("not established", "not applicable")
overlapped its text. In a real browser, with the real stylesheet, on a real v2 page."""

import pytest

PLAIN = "update dcim/devices #1 s1: changes nothing (sent; every value already held)"
STEPS = (
    "var part = document.createElement('div'); part.className = 'op-part';"
    "part.innerHTML = '<h3>What will be written to NetBox</h3><div>"
    "<ol class=\"set-steps mono small\" id=\"plain\"><li>" + PLAIN + "</li></ol>"
    "<ol class=\"set-steps\" id=\"badged\"><li><span class=\"badge badge-warn\">not established"
    "</span> <span class=\"txt\">what the database takes with each delete</span></li>"
    "<li><span class=\"badge badge-neutral\">not applicable</span> <span class=\"txt\">"
    "a second check</span></li>"
    "<li><span class=\"badge badge-ok\">passed</span> <span class=\"txt\">a short badge</span>"
    "</li></ol></div>';"
    "document.querySelector('main').appendChild(part); return 1")


def test_a_plain_line_is_one_line_and_a_badge_never_overlaps_its_text():
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    with browser.Served(A.app) as srv:
        with browser.Browser() as b:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 900})
            b.go(srv.url("/v2/"))
            b.wait_for("return document.querySelector('main')", 15)
            b.js(STEPS)
            got = b.js(
                "var li = document.querySelector('#plain li');"
                "var lh = parseFloat(getComputedStyle(li).lineHeight) || 18;"
                "var rows = [];"
                "document.querySelectorAll('#badged li').forEach(function (l) {"
                "  var bd = l.querySelector('.badge').getBoundingClientRect();"
                "  var tx = l.querySelector('.txt').getBoundingClientRect();"
                "  var be = l.querySelector('.badge');"
                "  rows.push([be.textContent, bd.right, tx.left, be.scrollWidth, be.clientWidth]);"
                "});"
                "return {plain_h: li.getBoundingClientRect().height, line_h: lh,"
                "        plain_w: li.getBoundingClientRect().width, rows: rows}")
            b.go("about:blank")
    # One line of about 75 characters at 1280 px: never a word per line.
    assert got["plain_h"] <= 2.2 * got["line_h"], got
    for text, badge_right, text_left, scroll_w, client_w in got["rows"]:
        # The badge's words fit inside it (they ran past its 76 px box into the text: W3's
        # screenshot 24), and the box ends before the text begins.
        assert scroll_w <= client_w + 1, (text, scroll_w, client_w)
        assert badge_right <= text_left + 0.5, (text, badge_right, text_left)
