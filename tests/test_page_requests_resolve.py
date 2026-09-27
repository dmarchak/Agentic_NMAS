"""Every request a page makes reaches a route: the reverse of reachability.

`test_route_reachability.py` asks whether a page reaches every route. Nothing
asked the reverse, so a `fetch('/removed/route')` left behind by a removal was
caught only if somebody had pinned that one route by path. Measured
2026-09-27 (C104's follow-up): a deliberate `fetch('/git/commit')` in a shipped
script failed ONE test in 4,878, the pin written for that route that morning;
for any other removed route nothing would have. `check_removed_definitions.py`
matches names, never paths.

The population is every literal request in the rendered pages and the scripts
they load (`route_references.page_requests`): 143 distinct at the time of
writing, all resolving. What it cannot see is stated in that function.
"""

import pytest

from tests import route_references as rr


@pytest.fixture(scope="module")
def requests():
    import app as A

    mp = pytest.MonkeyPatch()
    try:
        text = rr.corpus(A, mp)
    finally:
        mp.undo()
    return A, rr.page_requests(text)


def test_the_scan_finds_the_population(requests):
    _A, found = requests
    assert len(found) >= 120, len(found)
    assert ("/deploy/plan", "POST") in found           # a positive anchor


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
    assert rr.resolves(A, "/ai/approvals/${id}/${action}", "POST")
    assert not rr.resolves(A, "/ai/approvals/${id}/${action}", "DELETE")
