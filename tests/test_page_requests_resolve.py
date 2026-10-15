"""Every request a page makes reaches a route: the reverse of reachability.

`test_route_reachability.py` asks whether a page reaches every route. Nothing
asked the reverse, so a `fetch('/removed/route')` left behind by a removal was
caught only if somebody had pinned that one route by path. Measured
2026-09-27 (C104's follow-up): a deliberate `fetch('/git/commit')` in a shipped
script failed ONE test in 4,878, the pin written for that route that morning;
for any other removed route nothing would have. `check_removed_definitions.py`
matches names, never paths.

The population is every literal request in the rendered pages and the scripts
they load (`route_references.page_requests`; the pages are tests/interface_pages.py's):
143 distinct at the time of writing, on today's pages; 362 on 2026-10-15 when v2's pages
joined them (P7-19), all resolving. What it cannot see is stated in that function.
"""

import pytest

from tests import interface_pages
from tests import route_references as rr


@pytest.fixture(scope="module")
def requests():
    import app as A

    return A, rr.page_requests(rr.corpus())


def test_the_scan_finds_the_population(requests):
    _A, found = requests
    # Until P7-19 (2026-10-15) the population was today's two pages' (67 that day, falling as
    # they shrank). Now the floor is v2's alone, so removing today's pages moves nothing:
    # 298 distinct requests on v2's 119 pages and their scripts, measured 2026-10-15 (362
    # with today's pages).
    v2 = rr.page_requests(interface_pages.v2_corpus())
    assert len(v2) >= 250, len(v2)
    assert set(v2) <= set(found)
    assert ("/update/check", None) in v2                # a data-url its script sends
    assert ("/v2/device/r3/ask", "POST") in v2          # an hx-post (the device's Ask tab)


def test_an_htmx_request_is_read_with_its_verb():
    """v2's requests are htmx attributes: each read with its own verb, and a request whose
    method cannot be read (a `data-url` a script sends) is held to ANY method, never GET."""
    page = ('<button hx-post="/v2/a">x</button><a href="/v2/b" hx-get="/v2/c">y</a>'
            '<span hx-delete="/v2/d"></span><span data-url="/update/check"></span>')
    assert rr.page_requests(page) == {("/v2/a", "POST"): True, ("/v2/b", "GET"): True,
                                      ("/v2/c", "GET"): True, ("/v2/d", "DELETE"): True,
                                      ("/update/check", None): True}


def test_every_request_reaches_a_route(requests):
    A, found = requests
    dead = sorted(f"{m} {p}" for (p, m) in found if not rr.resolves(A, p, m))
    assert not dead, ("a page requests a route that does not exist (removed, "
                      f"or its method changed): {dead}")


def test_the_resolver_can_say_no():
    """The control, in the shape that went undetected: a removed route, a
    removed method, and the assembled form with its placeholders."""
    import app as A

    assert not rr.resolves(A, "/git/commit", "POST")
    assert not rr.resolves(A, "/device/192.0.2.1/delete", "POST")
    assert rr.resolves(A, "/git/commit/${hash}", "GET")
    assert rr.resolves(A, "/v2/settings/installation/diagnostics/drift/${n}/${to}", "POST")
    assert not rr.resolves(A, "/v2/settings/installation/diagnostics/drift/${n}/${to}",
                           "DELETE")
