"""Needs attention's "Mercury itself", opened, in a real browser (the operator, 2026-11-28:
"Large amounts of whitespace when 'Mercury itself' is expanded"). Its list was drawn with
`tl-record`, the two-column grid of a record's labels and values, so each row became a grid cell:
the first as wide as its whole unwrapped line, running past the page, the second squeezed into the
column beside it. Each row is now one item of a plain list, one under another, each wrapping
inside the section.
"""

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401

pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

LONG = ("The scheduled job coverage-nightly failed: its newest scheduled run, #62 of 06:07, ended "
        "failure; no success in its last 10 scheduled runs, since Nov 18 05:16; failed at Test "
        "the coverage ratchet, and every run before it the same way")


def _row(n, what):
    return {"id": f"scheduled:job-{n}", "level": "warning", "what": what,
            "source": "scheduled", "since": "2026-11-27T06:07:00Z", "devices": [],
            "action": {}, "clears": "when its next scheduled run passes, or acknowledged",
            "clears_at": None, "cause": "", "operands": [], "attached": [],
            "read_at": "2026-11-27T06:08:00Z", "acknowledge": True, "event": f"e-{n}"}


@pytest.fixture
def two_about_mercury(monkeypatch):
    from routes import v2
    real = v2._attention

    def with_rows():
        a = dict(real())
        a["mercury"] = [_row(1, LONG), _row(2, "The scheduled job mutation-weekly failed")]
        return a
    monkeypatch.setattr(v2, "_attention", with_rows)


def test_its_rows_wrap_one_under_another_inside_the_section(served, two_about_mercury):  # noqa: F811
    srv, b = served
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 900})
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    b.click('details[data-keep="mercury-itself"] > summary')
    b.wait_for("return document.querySelector('details[data-keep=\"mercury-itself\"]').open", 5)
    got = b.js(
        "var d = document.querySelector('details[data-keep=\"mercury-itself\"]');"
        "var box = d.getBoundingClientRect();"
        "var items = Array.from(d.querySelectorAll('li[data-mercury]')).map(function (li) {"
        "  var r = li.getBoundingClientRect();"
        "  return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width}; });"
        "return {box: {left: box.left, right: box.right, width: box.width}, items: items,"
        " page: [document.documentElement.scrollWidth, document.documentElement.clientWidth]};")
    first, second = got["items"]
    box = got["box"]
    assert first["right"] <= box["right"] + 1 and second["right"] <= box["right"] + 1, got
    assert abs(first["left"] - second["left"]) <= 1, "one under another, never side by side"
    assert second["top"] >= first["bottom"] - 1, got
    assert second["width"] >= box["width"] * 0.6, "the second row is never squeezed beside it"
    assert got["page"][0] <= got["page"][1], "nothing runs past the page"
