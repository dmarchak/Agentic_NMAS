"""The app's HTML is never cacheable; its static assets are, and are versioned.

Stage 7 §6c, and it exists because of a measured incident: the Baselines
panel drew a bare *"9 device(s)"* while `/golden/baselines` returned
`partial: true`. Cloudflare was serving stale HTML while the JSON came
through fresh, **and a browser hard-reload does not bypass the edge**. It
cost an hour and a wrong diagnosis on a page somebody knew well.

**The header rather than a Cache Rule at the zone**: a purge-per-deploy is a
human step in an external system, invisible when skipped, and the state it
produces — *"the page is wrong and the API is right"* — reads as a code
defect to everyone who meets it. This project refuses that shape everywhere
else.
"""

import os
import re

import pytest


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("NMAS_HEADLESS", "1")
    import app as nmas

    return nmas.app.test_client()


class TestHTMLIsNeverReusedWithoutAsking:
    def test_it_carries_no_cache(self, client):
        cc = client.get("/").headers.get("Cache-Control", "")
        assert "no-cache" in cc
        assert "must-revalidate" in cc

    def test_and_NOT_no_store(self, client):
        """`no-store` forbids keeping a copy, so every navigation is a full
        re-download of a third of a megabyte. `no-cache` keeps it and
        revalidates."""
        assert "no-store" not in client.get("/").headers.get("Cache-Control", "")

    def test_it_carries_a_validator(self, client):
        """Without one, `no-cache` IS a re-download — measured: before this,
        the page had no ETag, no Last-Modified and no Cache-Control at
        all."""
        assert client.get("/").headers.get("ETag")

    def test_an_unchanged_page_revalidates_to_304_and_zero_bytes(self, client):
        """**The whole reason for `no-cache` over `no-store`**, asserted as
        bytes rather than as a header."""
        first = client.get("/")
        again = client.get("/", headers={"If-None-Match": first.headers["ETag"]})

        assert again.status_code == 304
        assert len(again.get_data()) == 0
        assert len(first.get_data()) > 100_000, "the page is suspiciously small"


class TestStaticAssetsKeepALongLifetime:
    """**The constraint that would otherwise undo §0b.** A blanket no-cache
    over `/static/` would re-send the 275 KB of extracted script on every
    navigation, in the commit whose purpose was to stop exactly that."""

    def _a_versioned_asset(self, client):
        html = client.get("/").get_data(as_text=True)
        m = re.search(r"/static/(js/gen/[\w.]+\.js)\?v=(\d+)", html)
        assert m, "no versioned static URL in the page"
        return m

    def test_the_page_references_versioned_asset_urls(self, client):
        self._a_versioned_asset(client)

    def test_a_versioned_asset_is_cached_for_a_month(self, client):
        m = self._a_versioned_asset(client)
        cc = client.get(f"/static/{m.group(1)}?v={m.group(2)}") \
                   .headers.get("Cache-Control", "")

        assert "public" in cc and "max-age=" in cc
        assert int(re.search(r"max-age=(\d+)", cc).group(1)) >= 60 * 60 * 24 * 7

    def test_an_UNVERSIONED_asset_is_not(self, client):
        """**The half that makes the other half safe.** A long lifetime on a
        URL nobody versions is the HTML problem one layer down: a deploy
        changes the file and every browser keeps the old one for a month.
        Two files in `base.html` reference `/static/...` literally, so this
        is a live path and not a hypothetical."""
        cc = client.get("/static/js/bootstrap.bundle.min.js") \
                   .headers.get("Cache-Control", "")

        assert "max-age=2592000" not in cc
        assert "no-cache" in cc

    def test_the_header_is_ASSIGNED_not_defaulted(self):
        """Flask's static handler already sets `Cache-Control: no-cache`, so
        a `setdefault` did nothing and measured as `no-cache` on a 27 KB
        extracted script. Caught by measuring the response, not by reading
        the code.

        **Parsed, not grepped** — the branch's own comment explains the
        defect using the word `setdefault`, and the first version of this
        test matched that. Fourth time tonight: the better the comment, the
        more likely it quotes the code it explains.
        """
        import ast
        import inspect
        import textwrap

        import app as nmas

        tree = ast.parse(textwrap.dedent(inspect.getsource(nmas._cache_policy)))
        branches = [n for n in ast.walk(tree)
                    if isinstance(n, ast.If)
                    and "startswith" in ast.dump(n.test)]
        assert branches, "the static branch is not there"

        calls = {getattr(n.func, "attr", "")
                 for n in ast.walk(branches[0]) if isinstance(n, ast.Call)}
        assert calls, "the parse found no calls at all"
        assert "setdefault" not in calls, \
            "the static branch defaults again, so Flask's no-cache wins"


class TestJSONSaysItIsNotCacheable:
    """Confirmed rather than assumed, as asked.

    **Measured before deciding:** JSON responses carried no `Cache-Control`,
    no `ETag` and no `Last-Modified`, and the edge did not cache them —
    which is why the API stayed fresh while the page went stale. *That
    freshness was somebody else's default, not our policy*, and the whole
    argument for putting this in the app rather than in a Cache Rule is not
    to depend on one.
    """

    def test_a_json_read_is_no_store(self, client):
        r = client.get("/identity/status")
        assert r.mimetype == "application/json"
        assert r.headers.get("Cache-Control") == "no-store"

    def test_it_does_not_break_the_response(self, client):
        """Harmless, checked rather than asserted: the body is unchanged and
        still parses."""
        import json

        r = client.get("/identity/status")
        assert r.status_code == 200
        assert isinstance(json.loads(r.get_data(as_text=True)), dict)

    def test_a_route_that_sets_its_own_is_not_overridden(self):
        """`setdefault`, deliberately, on this branch only: a route that has
        thought about its own caching has thought harder than a blanket
        rule."""
        import inspect

        import app as nmas

        src = inspect.getsource(nmas._cache_policy)
        tail = src[src.index("application/json"):]
        assert "setdefault" in tail


class TestTheTwoHalvesAreOpposites:
    def test_html_and_static_do_not_get_the_same_policy(self, client):
        """§0b moved 275 KB of script out of the HTML precisely so the two
        could differ. If they ever converge, one of them is wrong."""
        html_cc = client.get("/").headers.get("Cache-Control", "")
        m = re.search(r"/static/(js/gen/[\w.]+\.js)\?v=(\d+)",
                      client.get("/").get_data(as_text=True))
        asset_cc = client.get(f"/static/{m.group(1)}?v={m.group(2)}") \
                         .headers.get("Cache-Control", "")

        assert html_cc != asset_cc
        assert "no-cache" in html_cc and "public" in asset_cc
